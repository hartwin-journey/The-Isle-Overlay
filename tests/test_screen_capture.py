import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication, QImage, QPixmap

from core.screen_capture import CaptureRegion, ScreenCaptureError, ScreenCaptureService


def test_capture_region_round_trips_to_qt_geometry_and_dictionary():
    region = CaptureRegion(-20, 30, 100, 40)

    assert region.to_qrect().getRect() == (-20, 30, 100, 40)
    assert region.to_dict() == {"x": -20, "y": 30, "width": 100, "height": 40}
    assert not CaptureRegion(0, 0, 31, 16).is_valid


def test_screen_capture_validation_rejects_invalid_or_off_screen_region(monkeypatch):
    service = ScreenCaptureService()
    with pytest.raises(ScreenCaptureError, match="at least"):
        service.validate_region(CaptureRegion(0, 0, 31, 16))

    monkeypatch.setattr(service, "screen_for_region", lambda region: None)
    with pytest.raises(ScreenCaptureError, match="inside one monitor"):
        service.validate_region(CaptureRegion(0, 0, 32, 16))


def test_ocr_png_preprocessing_encodes_and_enlarges_an_in_memory_image():
    QGuiApplication.instance() or QGuiApplication([])
    image = QImage(40, 20, QImage.Format.Format_RGB32)
    image.fill(0)

    payload = ScreenCaptureService.png_bytes_for_ocr(QPixmap.fromImage(image))
    prepared = QImage.fromData(payload, "PNG")

    assert payload.startswith(b"\x89PNG")
    assert (prepared.width(), prepared.height()) == (120, 60)
