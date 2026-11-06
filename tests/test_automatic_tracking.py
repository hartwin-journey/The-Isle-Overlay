import pytest

from core.automatic_tracking import (
    AutomaticCoordinateTracker,
    CoordinateConfirmation,
    parse_coordinates_from_ocr,
)
from core.coordinate_parser import CoordinateParseError, ParsedCoordinates
from core.screen_capture import CaptureRegion


class FakeOcrEngine:
    def support_status(self):
        return True, "available"

    def recognize_png(self, png_bytes):
        return ""

    def close(self):
        return None


def test_ocr_text_uses_existing_strict_parser_and_harmless_normalization():
    parsed = parse_coordinates_from_ocr(
        "Location\n−88,879.526, 288,696.110, 21,112.882\nTab menu"
    )
    assert (parsed.x, parsed.y, parsed.z) == pytest.approx(
        (-88879.526, 288696.110, 21112.882)
    )


@pytest.mark.parametrize(
    "text",
    [
        "Asset Location\nLat: -47,020.760 Alt: 32,374.064\nLong: 91,091.448",
        "Asset Location Lat: -47,020.760 Ait: 32,374.064 Long: 91,091.448",
        "Asset Location  Lat=-47,020.760  Long=91,091.448  Alt=32,374.064",
        "Latitude: -47,020.760\nLongitude: 91,091.448\nAltitude: 32,374.064",
    ],
)
def test_ocr_text_accepts_status_report_lat_long_alt_layout(text):
    parsed = parse_coordinates_from_ocr(text)
    assert (parsed.x, parsed.y, parsed.z) == pytest.approx(
        (-47020.760, 91091.448, 32374.064)
    )


@pytest.mark.parametrize(
    "text",
    [
        "ordinary OCR text",
        "88,879.526, 288,696.110, 21,112.882\n1, 2, 3",
        "88,879.S26, 288,696.110, 21,112.882",
        "Lat: -47,020.760 Alt: 32,374.O64 Long: 91,091.448",
        "Lat: 1 Lat: 2 Long: 3 Alt: 4",
        # Tesseract occasionally drops a decimal point at small font sizes.
        "Lat: -572,924 486 Alt: 6,124.100\nLong: -45,965.656",
        "Lat: 280,622.548 Alt: 44 756.942\nLong: 374,662.699",
    ],
)
def test_ocr_text_rejects_missing_ambiguous_or_uncertain_values(text):
    with pytest.raises(CoordinateParseError):
        parse_coordinates_from_ocr(text)


def test_confirmation_accepts_movement_but_rejects_large_inconsistent_jumps():
    confirmation = CoordinateConfirmation(required_reads=2)
    first = ParsedCoordinates(100, 200, 300)
    second = ParsedCoordinates(101, 200, 300)
    third = ParsedCoordinates(102, 200, 300)
    far = ParsedCoordinates(200_000, 200, 300)

    assert confirmation.observe(first) == "pending"
    confirmation.reset_candidate()
    assert confirmation.observe(first) == "pending"
    assert confirmation.observe(second) == "emit"
    assert confirmation.observe(second) == "duplicate"
    assert confirmation.observe(far) == "pending"
    assert confirmation.observe(first) == "pending"
    assert confirmation.observe(third) == "emit"


def test_tracker_emits_only_after_two_valid_identical_ocr_results():
    tracker = AutomaticCoordinateTracker(FakeOcrEngine())  # type: ignore[arg-type]
    received = []
    tracker.position_detected.connect(received.append)

    valid = "10, 20, 30"
    tracker.process_ocr_text(valid)
    assert received == []
    tracker.process_ocr_text(valid)
    assert len(received) == 1
    tracker.process_ocr_text(valid)
    tracker.process_ocr_text(valid)
    assert len(received) == 1


def test_tracker_emits_latest_position_from_two_plausible_moving_reads():
    tracker = AutomaticCoordinateTracker(FakeOcrEngine())  # type: ignore[arg-type]
    received = []
    tracker.position_detected.connect(received.append)

    tracker.process_ocr_text(
        "Asset Location\nLat: -47,020.760 Alt: 32,374.064\nLong: 91,091.448"
    )
    tracker.process_ocr_text(
        "Asset Location\nLat: -46,920.760 Alt: 32,375.064\nLong: 91,191.448"
    )

    assert len(received) == 1
    assert (received[0].x, received[0].y, received[0].z) == pytest.approx(
        (-46920.760, 91191.448, 32375.064)
    )


def test_capture_region_mapping_requires_a_usable_size():
    assert CaptureRegion.from_mapping({"x": -50, "y": 20, "width": 600, "height": 80}) == (
        CaptureRegion(-50, 20, 600, 80)
    )
    assert CaptureRegion.from_mapping({"x": 0, "y": 0, "width": 0, "height": 0}) is None
    assert CaptureRegion.from_mapping({"x": 0, "y": 0, "width": "bad", "height": 20}) is None


# --- Stall recovery, jump guard and capture failures -----------------------

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QGuiApplication, QPixmap
from PySide6.QtWidgets import QApplication

from core.screen_capture import (
    CaptureBackendUnavailable,
    ScreenCaptureError,
    ScreenCaptureService,
)


def test_large_jump_needs_more_reads_but_normal_movement_does_not():
    confirmation = CoordinateConfirmation(required_reads=2, jump_reads=4)
    base = ParsedCoordinates(-298_000, 55_000, 20_900)
    assert confirmation.observe(base, now=0.0) == "pending"
    assert confirmation.observe(base, now=0.9) == "emit"

    # A misread 450k away that repeats for two frames is held back...
    misread = ParsedCoordinates(-298_800, 513_342, 20_750)
    assert confirmation.observe(misread, now=1.8) == "pending"
    assert confirmation.observe(misread, now=2.7) == "pending"
    # ...and a normal nearby read afterwards is accepted as usual.
    near = ParsedCoordinates(-299_100, 49_156, 20_676)
    assert confirmation.observe(near, now=3.6) == "pending"
    assert confirmation.observe(near, now=4.5) == "emit"

    # A real teleport (respawn) is accepted after four consistent reads.
    respawn = ParsedCoordinates(-81_738, 417_593, 25_385)
    states = [confirmation.observe(respawn, now=5.4 + 0.9 * i) for i in range(4)]
    assert states == ["pending", "pending", "pending", "emit"]


def test_long_gaps_allow_large_moves_with_normal_confirmation():
    confirmation = CoordinateConfirmation(required_reads=2, jump_reads=4)
    confirmation.observe(ParsedCoordinates(0, 0, 0), now=0.0)
    confirmation.observe(ParsedCoordinates(0, 0, 0), now=1.0)
    far = ParsedCoordinates(300_000, 0, 0)  # reachable in 10 minutes
    assert confirmation.observe(far, now=600.0) == "pending"
    assert confirmation.observe(far, now=601.0) == "emit"


class _NeverRunningPool:
    """Thread pool stand-in that loses every job, like a dropped result."""

    def __init__(self):
        self.started = []

    def start(self, worker):
        self.started.append(worker)


class _WhiteCapture(ScreenCaptureService):
    def __init__(self):
        super().__init__(backends=[])

    def validate_region(self, region):
        return None

    def support_status(self):
        return True, "ok"

    def capture(self, region):
        pixmap = QPixmap(region.width, region.height)
        pixmap.fill(QColor("white"))
        return pixmap


def test_tracker_recovers_when_an_ocr_result_never_arrives(monkeypatch):
    QApplication.instance() or QApplication([])
    tracker = AutomaticCoordinateTracker(FakeOcrEngine(), _WhiteCapture())  # type: ignore[arg-type]
    pool = _NeverRunningPool()
    tracker._thread_pool = pool
    tracker.start(CaptureRegion(0, 0, 100, 40))
    tracker._poll()
    assert len(pool.started) == 1 and tracker._busy

    tracker._poll()  # still within the timeout: keep waiting
    assert len(pool.started) == 1

    monkeypatch.setattr(AutomaticCoordinateTracker, "STALL_TIMEOUT_S", 0.0)
    stale_sequence = pool.started[0].sequence
    tracker._poll()  # timed out: abandon it and capture again
    assert len(pool.started) == 2
    assert pool.started[1].sequence != stale_sequence

    # A late result from the abandoned read is ignored.
    tracker._on_ocr_finished(stale_sequence, "10, 20, 30", None)
    assert tracker._busy
    tracker.stop()


class _FlakyBackend:
    name = "flaky"

    def __init__(self):
        self.fail = False

    def grab(self, rect):
        if self.fail:
            raise CaptureBackendUnavailable("compositor hiccup")
        pixmap = QPixmap(rect.width(), rect.height())
        pixmap.fill(QColor("white"))
        return pixmap


def test_a_capture_method_that_worked_is_never_dropped():
    QApplication.instance() or QApplication([])
    backend = _FlakyBackend()
    service = ScreenCaptureService([backend])
    screen = QGuiApplication.primaryScreen().geometry()
    region = CaptureRegion(screen.x(), screen.y(), 100, 40)
    service.capture(region)
    backend.fail = True
    with pytest.raises(ScreenCaptureError) as info:
        service.capture(region)
    assert not isinstance(info.value, CaptureBackendUnavailable)
    assert service.backends == [backend]
    backend.fail = False
    assert service.capture(region).width() == 100


def test_capture_failure_during_tracking_keeps_tracking_enabled():
    QApplication.instance() or QApplication([])

    class Failing(_WhiteCapture):
        def capture(self, region):
            raise CaptureBackendUnavailable("no capture right now")

    tracker = AutomaticCoordinateTracker(FakeOcrEngine(), Failing())  # type: ignore[arg-type]
    unavailable = []
    tracker.unavailable.connect(unavailable.append)
    tracker.start(CaptureRegion(0, 0, 100, 40))
    tracker._poll()
    assert tracker.enabled and not tracker._busy and unavailable == []
    tracker.stop()


def test_an_unreadable_frame_does_not_discard_a_pending_read():
    confirmation = CoordinateConfirmation(required_reads=2)
    first = ParsedCoordinates(100, 200, 300)
    assert confirmation.observe(first, now=0.0) == "pending"
    confirmation.note_unreadable(now=0.9)  # e.g. a clipped or blurred frame
    assert confirmation.observe(first, now=1.8) == "emit"


def test_a_pending_read_expires_after_a_long_unreadable_stretch():
    confirmation = CoordinateConfirmation(required_reads=2)
    first = ParsedCoordinates(100, 200, 300)
    assert confirmation.observe(first, now=0.0) == "pending"
    confirmation.note_unreadable(now=CoordinateConfirmation.CANDIDATE_TTL_S + 1)
    assert confirmation.observe(first, now=CoordinateConfirmation.CANDIDATE_TTL_S + 2) == "pending"


# Real OCR output from a tightly drawn box that clipped the label letters.
CLIPPED_LABELS = "I_Et: -208,961.288  Alt: 31,943.436\nong: 256,940.141"


def test_clipped_labels_are_read_by_panel_layout():
    parsed = parse_coordinates_from_ocr(CLIPPED_LABELS)
    assert (parsed.x, parsed.y, parsed.z) == pytest.approx(
        (-208961.288, 256940.141, 31943.436)
    )


def test_labels_clipped_past_the_colon_are_read_by_panel_layout():
    # Real OCR output on the respawn/mutation screen, where the panel shifts.
    parsed = parse_coordinates_from_ocr(
        "it -22,654.625 Alt: 39,951.011 C\nNg: -203,162.625 :"
    )
    assert (parsed.x, parsed.y, parsed.z) == pytest.approx(
        (-22654.625, -203162.625, 39951.011)
    )


@pytest.mark.parametrize(
    "text",
    [
        # Real OCR output from a padded box: grouping or decimal point lost.
        "KM/h  Lat: -208,961288  Alt: 31943.436 Offici:\n6 Long: 256,940.141 # Play",
        ") KM/h  Lat: -208,961.288  Alt: 31943436 Offici\n51 Long: 256,940.141 # Play",
        # Clipped on the right: an incomplete number is never accepted.
        "at: -241,279.78 Alt: 51,778.704\nong: 265,140.407",
        "at: -241,279.788 Alt: 51,778.704\nong: 265,140.4",
        # Real respawn-screen reads with a damaged altitude.
        "it -22,654.625 Alt: 39951.011 C\nng: -203,162.625 i",
        "Lat: -22,654.625 Alt: 39,951.0T11\nLong: -203,162.625",
        # Two candidate Long lines: ambiguous.
        "at: -1,000.000 Alt: 2,000.000\nong: 3,000.000\nong: 4,000.000",
    ],
)
def test_layout_reading_never_accepts_damaged_or_ambiguous_numbers(text):
    with pytest.raises(CoordinateParseError):
        parse_coordinates_from_ocr(text)


def test_a_failure_streak_keeps_logging_what_ocr_sees(monkeypatch, caplog):
    import logging

    tracker = AutomaticCoordinateTracker(FakeOcrEngine())  # type: ignore[arg-type]
    clock = [1000.0]
    monkeypatch.setattr("core.automatic_tracking.time.monotonic", lambda: clock[0])
    with caplog.at_level(logging.INFO, logger="core.automatic_tracking"):
        for step in range(40):  # 40 unreadable frames, 0.9 s apart
            clock[0] = 1000.0 + 0.9 * step
            tracker.process_ocr_text(f"garbage frame {step}")
    reads = [r for r in caplog.records if r.getMessage().startswith("OCR read")]
    # First failure plus one every 15 s over ~35 s of failures.
    assert len(reads) == 3
