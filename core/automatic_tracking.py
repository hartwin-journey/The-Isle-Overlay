"""Optional pixel-only automatic coordinate tracking."""

from __future__ import annotations

import logging
import re
import time
from typing import Literal

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from core.coordinate_parser import (
    CoordinateParseError,
    ParsedCoordinates,
    parse_coordinates,
)
from core.local_ocr import OcrEngine, OcrRecognitionError, OcrUnavailableError
from core.models import Position
from core.screen_capture import (
    CaptureBackendUnavailable,
    CaptureRegion,
    ScreenCaptureError,
    ScreenCaptureService,
)

LOGGER = logging.getLogger(__name__)

_OCR_NUMBER = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"


def _single_labeled_ocr_value(text: str, labels: str) -> str | None:
    """Return one unambiguous labeled number without correcting OCR digits."""

    pattern = re.compile(
        rf"(?<![A-Za-z])(?:{labels})\s*[:=]\s*"
        # A value followed by a space and more digits means OCR split one
        # number (e.g. a dropped decimal point); never accept a fragment.
        rf"(?P<value>{_OCR_NUMBER})(?![\d.,A-Za-z])(?!\s+\d)",
        re.IGNORECASE,
    )
    values = [match.group("value") for match in pattern.finditer(text)]
    return values[0] if len(values) == 1 else None


# The game always prints coordinates with digit grouping and three decimals
# (e.g. -208,961.288). The layout fallback below accepts only this exact form.
_GAME_NUMBER = r"-?\d{1,3}(?:,\d{3})*\.\d{3}"
_ALT_LABEL = r"Alt(?:itude)?|Ait"


def _status_report_by_layout(text: str) -> tuple[str, str, str] | None:
    """Read the Lat/Alt and Long lines by position when a label is clipped.

    A capture box drawn tightly can cut the first letters off "Lat" and
    "Long", sometimes including the colon (OCR then sees e.g. "I_Et:", "it"
    or "ong:"). The panel layout is fixed: one line holds ``LAT  Alt: ALT``
    and another holds ``LONG``. Each value must be a complete, well-formed
    game number; nothing is repaired or guessed.
    """

    alt_lines = []
    long_lines = []
    alt_pattern = re.compile(
        rf"(?<![\d.,])(?P<lat>{_GAME_NUMBER})\s+(?:{_ALT_LABEL})\s*[:=]\s*"
        rf"(?P<alt>{_GAME_NUMBER})(?![\d.,])",
        re.IGNORECASE,
    )
    value_pattern = re.compile(rf"(?<![\d.,])(?P<value>{_GAME_NUMBER})(?![\d.,])")
    for line in text.splitlines():
        alt_match = alt_pattern.search(line)
        if alt_match:
            alt_lines.append((alt_match.group("lat"), alt_match.group("alt")))
            continue
        values = value_pattern.findall(line)
        if len(values) == 1:
            long_lines.append(values[0])
    if len(alt_lines) != 1 or len(long_lines) != 1:
        return None
    latitude, altitude = alt_lines[0]
    return latitude, long_lines[0], altitude


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
    # OCR engines commonly read the lowercase L in "Alt" as an uppercase I
    # in small UI fonts. This correction applies only to the known static label;
    # numeric OCR output is never guessed or repaired.
    altitude = _single_labeled_ocr_value(
        normalized,
        r"Alt(?:itude)?|Ait",
    )
    if latitude is None or longitude is None:
        by_layout = _status_report_by_layout(normalized)
        if by_layout is not None:
            latitude, longitude, altitude = by_layout
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
    """Confirm consecutive plausible reads and suppress exact duplicates.

    A position far from the last confirmed one (further than the player could
    have travelled in the elapsed time) needs ``jump_reads`` consistent reads
    instead of ``required_reads``. Real teleports such as respawning are still
    accepted after a few seconds, while a misread that repeats for two frames
    (e.g. a dropped digit separator) no longer moves the player across the map.
    """

    # Generous upper bound on travel speed, in world units per second.
    MAX_TRAVEL_SPEED = 2_000.0
    JUMP_ALLOWANCE = 10_000.0
    # A read that could not be parsed says nothing about the pending
    # candidate, so the candidate survives unreadable frames for this long.
    CANDIDATE_TTL_S = 4.0

    def __init__(
        self,
        required_reads: int = 2,
        max_confirmation_delta: float = 25_000.0,
        jump_reads: int = 4,
    ) -> None:
        self.required_reads = max(2, int(required_reads))
        self.jump_reads = max(self.required_reads, int(jump_reads))
        self.max_confirmation_delta = max(0.0, float(max_confirmation_delta))
        self._candidate: tuple[float, float, float] | None = None
        self._candidate_reads = 0
        self._candidate_at = 0.0
        self._last_emitted: tuple[float, float, float] | None = None
        self._last_emitted_at: float | None = None

    def note_unreadable(self, now: float | None = None) -> None:
        """Record a frame without coordinates; expire a stale candidate."""

        now = time.monotonic() if now is None else now
        if self._candidate is not None and now - self._candidate_at > self.CANDIDATE_TTL_S:
            self.reset_candidate()

    def is_jump(self, value: tuple[float, float, float], now: float) -> bool:
        """True if ``value`` is further than the player could have travelled."""
        if self._last_emitted is None or self._last_emitted_at is None:
            return False
        elapsed = max(0.0, now - self._last_emitted_at)
        allowed = self.JUMP_ALLOWANCE + self.MAX_TRAVEL_SPEED * elapsed
        dx = value[0] - self._last_emitted[0]
        dy = value[1] - self._last_emitted[1]
        return (dx * dx + dy * dy) ** 0.5 > allowed

    def reset_candidate(self) -> None:
        self._candidate = None
        self._candidate_reads = 0

    def observe(
        self, parsed: ParsedCoordinates, now: float | None = None
    ) -> Literal["pending", "emit", "duplicate"]:
        now = time.monotonic() if now is None else now
        value = (parsed.x, parsed.y, parsed.z)
        if value == self._last_emitted:
            self.reset_candidate()
            return "duplicate"
        self.note_unreadable(now)
        self._candidate_at = now
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
        needed = self.jump_reads if self.is_jump(value, now) else self.required_reads
        if self._candidate_reads < needed:
            return "pending"
        self._last_emitted = value
        self._last_emitted_at = now
        self.reset_candidate()
        return "emit"


class _OcrWorkerSignals(QObject):
    finished = Signal(int, object, object)


class _OcrWorker(QRunnable):
    def __init__(
        self,
        sequence: int,
        engine: OcrEngine,
        png_bytes: bytes,
        signals: _OcrWorkerSignals,
    ) -> None:
        super().__init__()
        self.sequence = sequence
        self.engine = engine
        self.png_bytes = png_bytes
        # Owned by the tracker, not the worker: a per-worker signal object can
        # be freed with the auto-deleted runnable before its queued result is
        # delivered, which would leave the tracker waiting forever.
        self.signals = signals

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

    # OCR normally takes well under a second and Tesseract is killed after
    # 10 s, so a read pending longer than this was lost.
    STALL_TIMEOUT_S = 15.0
    # Delay before the follow-up read that confirms a new position.
    CONFIRM_POLL_MS = 250
    # While reads keep failing, log what OCR sees at most this often.
    UNREADABLE_LOG_INTERVAL_S = 15.0

    def __init__(
        self,
        engine: OcrEngine,
        capture_service: ScreenCaptureService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.engine = engine
        self.capture_service = capture_service or ScreenCaptureService()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._thread_pool = QThreadPool.globalInstance()
        self._worker_signals = _OcrWorkerSignals(self)
        self._worker_signals.finished.connect(self._on_ocr_finished)
        # Workers stay referenced until they report back.
        self._workers: dict[int, _OcrWorker] = {}
        self._region: CaptureRegion | None = None
        self._confirmation = CoordinateConfirmation()
        self._busy = False
        self._busy_since = 0.0
        self._sequence = 0
        self._last_status = ""
        self._last_unreadable_log = 0.0

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
        supported, reason = self.capture_service.support_status()
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
        self._workers.clear()
        self._confirmation.reset_candidate()
        self._set_status("Automatic tracking: off")

    def close(self) -> None:
        self.stop()
        self.engine.close()

    @Slot()
    def _poll(self) -> None:
        if self._region is None or not self.enabled:
            return
        if self._busy:
            if time.monotonic() - self._busy_since < self.STALL_TIMEOUT_S:
                return
            # The previous read never reported back. Abandon it (its late
            # result is ignored via the sequence number) instead of waiting
            # forever, which used to stop tracking until a restart.
            LOGGER.warning(
                "Automatic tracking: no OCR result after %.0f s; retrying",
                self.STALL_TIMEOUT_S,
            )
            self._workers.pop(self._sequence, None)
            self._sequence += 1
            self._busy = False
        # Set before capturing: the Wayland portal waits in a nested event
        # loop, during which the timer could otherwise start a second poll.
        self._busy = True
        self._busy_since = time.monotonic()
        sequence = self._sequence
        try:
            pixmap = self.capture_service.capture(self._region)
            png_bytes = self.capture_service.png_bytes_for_ocr(pixmap)
        except CaptureBackendUnavailable as exc:
            # Capture worked when tracking started, so treat this as
            # temporary: keep polling and re-detect capture methods.
            if sequence == self._sequence:
                self._busy = False
                self._confirmation.note_unreadable()
                self.capture_service.reset_backends()
                self._set_status(
                    f"Automatic tracking: screen capture failed, retrying ({exc})"
                )
            return
        except ScreenCaptureError as exc:
            if sequence == self._sequence:
                self._busy = False
                self._confirmation.note_unreadable()
                self._set_status(f"Automatic tracking: {exc}")
            return
        if sequence != self._sequence or not self.enabled:
            # Stopped or restarted while the capture was in progress.
            return

        worker = _OcrWorker(sequence, self.engine, png_bytes, self._worker_signals)
        worker.setAutoDelete(False)
        self._workers[sequence] = worker
        self._thread_pool.start(worker)

    @Slot(int, object, object)
    def _on_ocr_finished(
        self,
        sequence: int,
        text: object,
        error: object,
    ) -> None:
        self._workers.pop(sequence, None)
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
            self._confirmation.note_unreadable()
            LOGGER.debug("Automatic tracking OCR error: %s", error)
            self._set_status("Automatic tracking: OCR could not read this frame")
            return
        self.process_ocr_text(str(text or ""))

    def process_ocr_text(self, text: str) -> None:
        """Process one OCR result; public for deterministic unit testing."""

        try:
            parsed = parse_coordinates_from_ocr(text)
        except CoordinateParseError as exc:
            self._confirmation.note_unreadable()
            status = "Automatic tracking: waiting for visible coordinates"
            now = time.monotonic()
            if (
                status != self._last_status
                or now - self._last_unreadable_log >= self.UNREADABLE_LOG_INTERVAL_S
            ):
                # Shows what the capture area contains during a failure
                # streak (e.g. a clipped box or other text in the way).
                self._last_unreadable_log = now
                seen = " | ".join(
                    line.strip() for line in text.splitlines() if line.strip()
                )[:120]
                LOGGER.info("OCR read %r (%s)", seen, exc)
            self._set_status(status)
            return

        state = self._confirmation.observe(parsed)
        if state == "pending" and self._confirmation.is_jump(
            (parsed.x, parsed.y, parsed.z), time.monotonic()
        ):
            LOGGER.debug(
                "Large jump to x=%.3f y=%.3f; waiting for more consistent reads",
                parsed.x,
                parsed.y,
            )
        if state == "pending":
            self._set_status("Automatic tracking: confirming coordinates")
            # Read again soon instead of waiting a full polling interval, so
            # a position confirms in about half a second.
            QTimer.singleShot(self.CONFIRM_POLL_MS, self._poll)
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
        # Status changes are infrequent (deduplicated); logging them makes a
        # stalled or failing tracker diagnosable from logs/companion.log.
        LOGGER.info("%s", value)
        self.status_changed.emit(value)
