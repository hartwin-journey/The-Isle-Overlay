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
