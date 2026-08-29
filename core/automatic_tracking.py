"""Optional pixel-only automatic coordinate tracking."""

from __future__ import annotations

import logging
import re
from typing import Literal

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from core.coordinate_parser import (
    CoordinateParseError,
    ParsedCoordinates,
    parse_coordinates,
)
from core.local_ocr import OcrRecognitionError, OcrUnavailableError, WindowsOcrEngine
from core.models import Position
from core.screen_capture import CaptureRegion, ScreenCaptureError, ScreenCaptureService

LOGGER = logging.getLogger(__name__)

_OCR_NUMBER = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"


def _single_labeled_ocr_value(text: str, labels: str) -> str | None:
    """Return one unambiguous labeled number without correcting OCR digits."""

    pattern = re.compile(
        rf"(?<![A-Za-z])(?:{labels})\s*[:=]\s*"
        rf"(?P<value>{_OCR_NUMBER})(?![\d.,A-Za-z])",
        re.IGNORECASE,
    )
    values = [match.group("value") for match in pattern.finditer(text)]
    return values[0] if len(values) == 1 else None


def parse_coordinates_from_ocr(text: str) -> ParsedCoordinates:
    """Validate OCR lines with the existing strict coordinate parser.

    Only harmless Unicode punctuation normalization is performed. Ambiguous
    output containing more than one distinct valid coordinate is rejected.
    """

    if not isinstance(text, str):
        raise CoordinateParseError("OCR result is not text")
    normalized = text.translate(
        str.maketrans(
            {
                "−": "-",
                "–": "-",
                "—": "-",
                "\u00a0": " ",
            }
        )
    )
    matches: dict[tuple[float, float, float], ParsedCoordinates] = {}
    for raw_line in normalized.splitlines() or [normalized]:
        line = " ".join(raw_line.split())
        if not line:
            continue
        try:
            parsed = parse_coordinates(line)
        except CoordinateParseError:
            continue
        matches[(parsed.x, parsed.y, parsed.z)] = parsed

    # The current status report presents the same world coordinates as
    # Lat/Long/Alt, often split across two OCR lines. Extract only explicitly
    # labeled numeric values, convert them to the canonical X/Y/Z form, and
    # still delegate final validation to the existing strict parser.
    latitude = _single_labeled_ocr_value(normalized, r"Lat(?:itude)?")
    longitude = _single_labeled_ocr_value(
        normalized,
        r"Long(?:itude)?|Lon",
    )
    # Windows OCR commonly reads the lowercase L in "Alt" as an uppercase I
    # in small UI fonts. This correction applies only to the known static label;
    # numeric OCR output is never guessed or repaired.
    altitude = _single_labeled_ocr_value(
        normalized,
        r"Alt(?:itude)?|Ait",
    )
    if latitude is not None and longitude is not None and altitude is not None:
        try:
            parsed = parse_coordinates(
                f"X={latitude}, Y={longitude}, Z={altitude}"
            )
        except CoordinateParseError:
            pass
        else:
            matches[(parsed.x, parsed.y, parsed.z)] = parsed
    if not matches:
        raise CoordinateParseError("OCR text does not contain a valid coordinate line")
    if len(matches) != 1:
        raise CoordinateParseError("OCR text contains multiple coordinate lines")
    return next(iter(matches.values()))


class CoordinateConfirmation:
    """Confirm consecutive plausible reads and suppress exact duplicates."""

    def __init__(
        self,
        required_reads: int = 2,
        max_confirmation_delta: float = 25_000.0,
    ) -> None:
        self.required_reads = max(2, int(required_reads))
        self.max_confirmation_delta = max(0.0, float(max_confirmation_delta))
        self._candidate: tuple[float, float, float] | None = None
        self._candidate_reads = 0
        self._last_emitted: tuple[float, float, float] | None = None

    def reset_candidate(self) -> None:
        self._candidate = None
        self._candidate_reads = 0

    def observe(
        self, parsed: ParsedCoordinates
    ) -> Literal["pending", "emit", "duplicate"]:
        value = (parsed.x, parsed.y, parsed.z)
        if value == self._last_emitted:
            self.reset_candidate()
            return "duplicate"
        if self._candidate is not None and max(
            abs(current - previous)
            for current, previous in zip(value, self._candidate)
        ) <= self.max_confirmation_delta:
            # Keep the newest position so moving players are not forced to
            # stand perfectly still for two polling intervals.
            self._candidate = value
            self._candidate_reads += 1
        else:
            self._candidate = value
            self._candidate_reads = 1
        if self._candidate_reads < self.required_reads:
            return "pending"
        self._last_emitted = value
        self.reset_candidate()
        return "emit"


class _OcrWorkerSignals(QObject):
    finished = Signal(int, object, object)


class _OcrWorker(QRunnable):
    def __init__(self, sequence: int, engine: WindowsOcrEngine, png_bytes: bytes) -> None:
        super().__init__()
        self.sequence = sequence
        self.engine = engine
        self.png_bytes = png_bytes
        self.signals = _OcrWorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            text = self.engine.recognize_png(self.png_bytes)
        except (OcrUnavailableError, OcrRecognitionError) as exc:
            self.signals.finished.emit(self.sequence, None, exc)
            return
        except Exception as exc:  # Keep an optional feature from taking down Qt.
            LOGGER.exception("Unexpected automatic OCR error")
            self.signals.finished.emit(
                self.sequence,
                None,
                OcrRecognitionError(str(exc)),
            )
            return
        self.signals.finished.emit(self.sequence, text, None)


class AutomaticCoordinateTracker(QObject):
    """Capture the configured pixels and emit only confirmed valid positions."""

    position_detected = Signal(object)
    status_changed = Signal(str)
    unavailable = Signal(str)

    def __init__(
        self,
        engine: WindowsOcrEngine,
        capture_service: ScreenCaptureService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.engine = engine
        self.capture_service = capture_service or ScreenCaptureService()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._thread_pool = QThreadPool.globalInstance()
        self._region: CaptureRegion | None = None
        self._confirmation = CoordinateConfirmation()
        self._busy = False
        self._sequence = 0
        self._last_status = ""

    @property
    def enabled(self) -> bool:
        return self._timer.isActive()

    def start(
        self,
        region: CaptureRegion,
        *,
        interval_ms: int = 900,
        confirmation_reads: int = 2,
    ) -> None:
        self.capture_service.validate_region(region)
        supported, reason = self.engine.support_status()
        if not supported:
            raise OcrUnavailableError(reason)
        self._timer.stop()
        self._region = region
        self._confirmation = CoordinateConfirmation(confirmation_reads)
        self._sequence += 1
        # A recognition request from the previous region may still finish in
        # the background. Its sequence is now stale, and must not prevent the
        # newly configured region from polling immediately.
        self._busy = False
        self._timer.start(min(5000, max(500, int(interval_ms))))
        self._set_status("Automatic tracking: scanning selected screen area")
        QTimer.singleShot(0, self._poll)

    def stop(self) -> None:
        self._timer.stop()
        self._sequence += 1
        self._busy = False
        self._confirmation.reset_candidate()
        self._set_status("Automatic tracking: off")

    def close(self) -> None:
        self.stop()
        self.engine.close()

    @Slot()
    def _poll(self) -> None:
        if self._busy or self._region is None or not self.enabled:
            return
        try:
            pixmap = self.capture_service.capture(self._region)
            png_bytes = self.capture_service.png_bytes_for_ocr(pixmap)
        except ScreenCaptureError as exc:
            self._confirmation.reset_candidate()
            self._set_status(f"Automatic tracking: {exc}")
            return

        self._busy = True
        worker = _OcrWorker(self._sequence, self.engine, png_bytes)
        worker.signals.finished.connect(self._on_ocr_finished)
        self._thread_pool.start(worker)

    @Slot(int, object, object)
    def _on_ocr_finished(
        self,
        sequence: int,
        text: object,
        error: object,
    ) -> None:
        if sequence != self._sequence:
            return
        self._busy = False
        if isinstance(error, OcrUnavailableError):
            self._timer.stop()
            reason = str(error)
            self._set_status(f"Automatic tracking unavailable: {reason}")
            self.unavailable.emit(reason)
            return
        if isinstance(error, OcrRecognitionError):
            self._confirmation.reset_candidate()
            self._set_status("Automatic tracking: OCR could not read this frame")
            return
        self.process_ocr_text(str(text or ""))

    def process_ocr_text(self, text: str) -> None:
        """Process one OCR result; public for deterministic unit testing."""

        try:
            parsed = parse_coordinates_from_ocr(text)
        except CoordinateParseError as exc:
            self._confirmation.reset_candidate()
            LOGGER.debug("Automatic OCR coordinate rejected: %s", exc)
            self._set_status("Automatic tracking: waiting for visible coordinates")
            return

        state = self._confirmation.observe(parsed)
        if state == "pending":
            self._set_status("Automatic tracking: confirming coordinates")
            return
        if state == "duplicate":
            self._set_status("Automatic tracking: coordinates unchanged")
            return

        position = Position.now(parsed.x, parsed.y, parsed.z)
        LOGGER.info(
            "Valid automatic coordinate update: x=%.3f y=%.3f z=%.3f",
            position.x,
            position.y,
            position.z,
        )
        self.position_detected.emit(position)
        self._set_status("Automatic tracking: position updated")

    def _set_status(self, value: str) -> None:
        if value == self._last_status:
            return
        self._last_status = value
        self.status_changed.emit(value)
