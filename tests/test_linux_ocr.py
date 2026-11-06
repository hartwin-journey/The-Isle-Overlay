import os
import stat

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPixmap

from core.local_ocr import (
    OcrRecognitionError,
    TesseractOcrEngine,
    WindowsOcrEngine,
    create_ocr_engine,
)
from core.screen_capture import (
    CaptureBackendUnavailable,
    CaptureRegion,
    PortalBackend,
    ScreenCaptureService,
)

posix_only = pytest.mark.skipif(os.name == "nt", reason="uses a POSIX shell stub")


def _stub(tmp_path, body: str):
    path = tmp_path / "tesseract"
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def test_factory_picks_platform_engine(tmp_path):
    engine = create_ocr_engine(tmp_path)
    expected = WindowsOcrEngine if os.name == "nt" else TesseractOcrEngine
    assert isinstance(engine, expected)


def test_missing_tesseract_reports_an_install_hint(tmp_path):
    engine = TesseractOcrEngine(str(tmp_path / "does-not-exist"))
    supported, reason = engine.support_status()
    assert supported is False
    assert "not installed" in reason


@posix_only
def test_tesseract_without_english_data_is_unavailable(tmp_path):
    stub = _stub(tmp_path, 'echo "List of available languages (1):"; echo osd\n')
    supported, reason = TesseractOcrEngine(str(stub)).support_status()
    assert supported is False
    assert "English language data" in reason


@posix_only
def test_tesseract_pipes_png_through_stdin_and_returns_stdout(tmp_path):
    received = tmp_path / "received.bin"
    stub = _stub(
        tmp_path,
        'if [ "$1" = "--list-langs" ]; then echo "List of available languages (2):"; '
        "echo eng; echo osd; exit 0; fi\n"
        f'cat > "{received}"\n'
        'echo "Lat: -47,020.760 Alt: 32,374.064"\necho "Long: 91,091.448"\n',
    )
    engine = TesseractOcrEngine(str(stub))
    assert engine.support_status()[0] is True
    text = engine.recognize_png(b"\x89PNG fake")
    assert received.read_bytes() == b"\x89PNG fake"
    assert "Long: 91,091.448" in text


@posix_only
def test_tesseract_failure_is_a_recognition_error(tmp_path):
    stub = _stub(
        tmp_path,
        'if [ "$1" = "--list-langs" ]; then echo eng; exit 0; fi\n'
        'echo "Error in pixReadMem" >&2; exit 1\n',
    )
    with pytest.raises(OcrRecognitionError, match="pixReadMem"):
        TesseractOcrEngine(str(stub)).recognize_png(b"data")


class _FailingBackend:
    name = "broken"

    def grab(self, rect):
        raise CaptureBackendUnavailable("not on this desktop")


class _SolidBackend:
    name = "solid"

    def __init__(self):
        self.calls = []

    def grab(self, rect):
        self.calls.append(QRect(rect))
        pixmap = QPixmap(rect.width(), rect.height())
        pixmap.fill(QColor("white"))
        return pixmap


def test_capture_falls_through_unavailable_backends():
    QGuiApplication.instance() or QGuiApplication([])
    solid = _SolidBackend()
    service = ScreenCaptureService([_FailingBackend(), solid])
    screen = QGuiApplication.primaryScreen().geometry()
    region = CaptureRegion(screen.x(), screen.y(), 100, 40)

    assert service.capture(region).size().width() == 100
    assert service.backend_name == "solid"
    service.capture(region)
    assert len(solid.calls) == 2


def test_capture_reports_when_no_backend_can_work():
    QGuiApplication.instance() or QGuiApplication([])
    service = ScreenCaptureService([_FailingBackend()])
    screen = QGuiApplication.primaryScreen().geometry()
    with pytest.raises(CaptureBackendUnavailable, match="grim"):
        service.capture(CaptureRegion(screen.x(), screen.y(), 100, 40))
    assert service.support_status()[0] is False


def test_portal_crop_maps_logical_region_into_device_pixels():
    QGuiApplication.instance() or QGuiApplication([])
    desktop = ScreenCaptureService.virtual_geometry()
    # Simulate a 2x scaled screenshot with a marker at logical (10, 20).
    image = QImage(desktop.width() * 2, desktop.height() * 2, QImage.Format.Format_RGB32)
    image.fill(QColor("black"))
    image.setPixelColor(20, 40, QColor("red"))
    cropped = PortalBackend._crop(
        image, QRect(desktop.x() + 10, desktop.y() + 20, 50, 30)
    ).toImage()
    assert (cropped.width(), cropped.height()) == (100, 60)
    assert cropped.pixelColor(0, 0) == QColor("red")
