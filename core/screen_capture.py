"""Ordinary Qt screen capture limited to a user-selected rectangle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from PySide6.QtCore import QBuffer, QIODevice, QRect, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPixmap, QScreen


class ScreenCaptureError(RuntimeError):
    """Raised when a configured region cannot be captured normally."""


@dataclass(frozen=True, slots=True)
class CaptureRegion:
    x: int
    y: int
    width: int
    height: int

    @classmethod
    def from_mapping(cls, value: object) -> "CaptureRegion | None":
        if not isinstance(value, Mapping):
            return None
        try:
            region = cls(
                x=int(value["x"]),
                y=int(value["y"]),
                width=int(value["width"]),
                height=int(value["height"]),
            )
        except (KeyError, TypeError, ValueError):
            return None
        return region if region.is_valid else None

    @property
    def is_valid(self) -> bool:
        return 32 <= self.width <= 4096 and 16 <= self.height <= 2160

    def to_qrect(self) -> QRect:
        return QRect(self.x, self.y, self.width, self.height)

    def to_dict(self) -> dict[str, int]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


class ScreenCaptureService:
    """Capture pixels without opening or inspecting any application process."""

    @staticmethod
    def virtual_geometry() -> QRect:
        screens = QGuiApplication.screens()
        if not screens:
            return QRect()
        geometry = QRect(screens[0].geometry())
        for screen in screens[1:]:
            geometry = geometry.united(screen.geometry())
        return geometry

    @staticmethod
    def screen_for_region(region: CaptureRegion) -> QScreen | None:
        target = region.to_qrect()
        for screen in QGuiApplication.screens():
            if screen.geometry().contains(target):
                return screen
        return None

    def validate_region(self, region: CaptureRegion) -> None:
        if not region.is_valid:
            raise ScreenCaptureError("Select an area at least 32 × 16 pixels.")
        if self.screen_for_region(region) is None:
            raise ScreenCaptureError("The capture area must stay inside one monitor.")

    def capture(self, region: CaptureRegion) -> QPixmap:
        self.validate_region(region)
        screen = self.screen_for_region(region)
        if screen is None:
            raise ScreenCaptureError("The configured monitor is unavailable.")
        screen_geometry = screen.geometry()
        pixmap = screen.grabWindow(
            0,
            region.x - screen_geometry.x(),
            region.y - screen_geometry.y(),
            region.width,
            region.height,
        )
        if pixmap.isNull():
            raise ScreenCaptureError("Windows returned an empty screen capture.")
        return pixmap

    @staticmethod
    def png_bytes_for_ocr(pixmap: QPixmap) -> bytes:
        """Create a larger grayscale PNG entirely in memory for OCR."""

        image = pixmap.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
        # Windows OCR is substantially more reliable with dark text on a light
        # background. The game's coordinate panel normally uses the opposite.
        # Sample a tiny copy and invert only predominantly dark captures.
        sample = image.scaled(
            32,
            32,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        average_brightness = sum(
            sample.pixelColor(x, y).value()
            for y in range(sample.height())
            for x in range(sample.width())
        ) / max(1, sample.width() * sample.height())
        if average_brightness < 128:
            image.invertPixels(QImage.InvertMode.InvertRgb)
        longest = max(image.width(), image.height())
        if longest < 1600:
            scale = min(3.0, 1600.0 / max(1, longest))
            image = image.scaled(
                max(1, round(image.width() * scale)),
                max(1, round(image.height() * scale)),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        buffer = QBuffer()
        if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
            raise ScreenCaptureError("Could not allocate the in-memory OCR image.")
        try:
            if not image.save(buffer, "PNG"):
                raise ScreenCaptureError("Could not encode the in-memory OCR image.")
            return bytes(buffer.data())
        finally:
            buffer.close()
