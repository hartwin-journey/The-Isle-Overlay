"""Ordinary screen capture limited to a user-selected rectangle.

Windows, macOS and X11 use Qt's normal screen grab. Wayland compositors do not
let applications read the screen that way, so Wayland sessions use ``grim``
(wlroots compositors such as Sway, Hyprland, niri and river) when it is
installed, then fall back to the standard xdg-desktop-portal Screenshot API
(GNOME, KDE Plasma, and any desktop with a portal).
"""

from __future__ import annotations

import logging
import os
import secrets
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from PySide6.QtCore import (
    SLOT,
    QBuffer,
    QEventLoop,
    QIODevice,
    QObject,
    QRect,
    Qt,
    QTimer,
    QUrl,
    Slot,
)
from PySide6.QtGui import QGuiApplication, QImage, QPixmap, QScreen

LOGGER = logging.getLogger(__name__)


class ScreenCaptureError(RuntimeError):
    """Raised when a configured region cannot be captured normally."""


class CaptureBackendUnavailable(ScreenCaptureError):
    """Raised when a capture method cannot work on this desktop at all."""


def is_wayland_session() -> bool:
    """True when the desktop is Wayland, even if Qt itself runs via XWayland."""

    platform = QGuiApplication.platformName().lower()
    if platform.startswith("wayland"):
        return True
    if platform in {"offscreen", "minimal", "windows", "cocoa"}:
        return False
    return bool(os.environ.get("WAYLAND_DISPLAY")) or (
        os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
    )


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


class CaptureBackend(Protocol):
    name: str

    def grab(self, rect: QRect) -> QPixmap: ...


class QtGrabBackend:
    """Qt's normal desktop grab (Windows, macOS, X11)."""

    name = "Qt screen grab"

    def grab(self, rect: QRect) -> QPixmap:
        screen = ScreenCaptureService.screen_for_rect(rect)
        if screen is None:
            raise ScreenCaptureError("The configured monitor is unavailable.")
        screen_geometry = screen.geometry()
        pixmap = screen.grabWindow(
            0,
            rect.x() - screen_geometry.x(),
            rect.y() - screen_geometry.y(),
            rect.width(),
            rect.height(),
        )
        if pixmap.isNull():
            raise ScreenCaptureError("The desktop returned an empty screen capture.")
        return pixmap


class GrimBackend:
    """wlroots screencopy via ``grim``; captures only the requested region."""

    name = "grim"

    def __init__(self, executable: str) -> None:
        self.executable = executable

    def grab(self, rect: QRect) -> QPixmap:
        geometry = f"{rect.x()},{rect.y()} {rect.width()}x{rect.height()}"
        try:
            result = subprocess.run(
                # PPM is uncompressed, so it is the cheapest format to pipe.
                [self.executable, "-g", geometry, "-t", "ppm", "-"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5.0,
            )
        except subprocess.TimeoutExpired as exc:
            raise ScreenCaptureError("grim did not respond in time.") from exc
        except OSError as exc:
            raise CaptureBackendUnavailable("grim could not be started.") from exc
        if result.returncode != 0:
            message = result.stderr.decode("utf-8", errors="replace").strip()
            # GNOME and KDE do not implement wlr-screencopy; grim fails at once.
            raise CaptureBackendUnavailable(message or "grim could not capture the screen.")
        pixmap = QPixmap()
        if not pixmap.loadFromData(result.stdout, "PPM"):
            raise ScreenCaptureError("grim returned an unreadable image.")
        return pixmap


class _PortalResponse(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.loop = QEventLoop()
        self.code: int | None = None
        self.results: dict[str, object] = {}

    @Slot("uint", "QVariantMap")
    def on_response(self, code: int, results: object) -> None:
        self.code = int(code)
        self.results = dict(results) if isinstance(results, Mapping) else {}
        self.loop.quit()


class PortalBackend:
    """xdg-desktop-portal Screenshot API, cropped to the requested region.

    The portal writes the screenshot to a temporary file and returns its URI;
    the file is read into memory and deleted immediately.
    """

    name = "desktop portal"
    _SERVICE = "org.freedesktop.portal.Desktop"
    _PATH = "/org/freedesktop/portal/desktop"

    def __init__(self) -> None:
        try:
            from PySide6.QtDBus import QDBusConnection
        except ImportError as exc:  # pragma: no cover - PySide6 always ships it
            raise CaptureBackendUnavailable("Qt D-Bus support is unavailable.") from exc
        self._bus = QDBusConnection.sessionBus()
        if not self._bus.isConnected():
            raise CaptureBackendUnavailable("The desktop session bus is unavailable.")

    def grab(self, rect: QRect) -> QPixmap:
        from PySide6.QtDBus import QDBusInterface, QDBusMessage

        token = "isle_companion_" + secrets.token_hex(8)
        sender = self._bus.baseService().lstrip(":").replace(".", "_")
        request_path = f"{self._PATH}/request/{sender}/{token}"
        response = _PortalResponse()
        # Subscribe before calling so a fast portal cannot answer unseen.
        if not self._bus.connect(
            self._SERVICE,
            request_path,
            "org.freedesktop.portal.Request",
            "Response",
            response,
            SLOT("on_response(uint,QVariantMap)"),
        ):
            raise CaptureBackendUnavailable("Could not listen for the screenshot portal.")
        try:
            interface = QDBusInterface(
                self._SERVICE,
                self._PATH,
                "org.freedesktop.portal.Screenshot",
                self._bus,
            )
            if not interface.isValid():
                raise CaptureBackendUnavailable(
                    "This desktop does not provide a screenshot portal."
                )
            reply = interface.call(
                "Screenshot", "", {"handle_token": token, "interactive": False}
            )
            if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                raise CaptureBackendUnavailable(
                    reply.errorMessage() or "The screenshot portal refused the request."
                )
            QTimer.singleShot(5000, response.loop.quit)
            if response.code is None:
                response.loop.exec()
        finally:
            self._bus.disconnect(
                self._SERVICE,
                request_path,
                "org.freedesktop.portal.Request",
                "Response",
                response,
                SLOT("on_response(uint,QVariantMap)"),
            )
        if response.code is None:
            raise ScreenCaptureError("The screenshot portal did not respond in time.")
        if response.code == 1:
            raise ScreenCaptureError("The screenshot permission was declined.")
        if response.code != 0:
            raise ScreenCaptureError("The screenshot portal could not capture the screen.")
        path = Path(QUrl(str(response.results.get("uri", ""))).toLocalFile())
        if not path.name:
            raise ScreenCaptureError("The screenshot portal returned no image.")
        try:
            image = QImage(str(path))
        finally:
            try:
                path.unlink()
            except OSError:
                pass
        if image.isNull():
            raise ScreenCaptureError("The screenshot portal returned an unreadable image.")
        return self._crop(image, rect)

    @staticmethod
    def _crop(image: QImage, rect: QRect) -> QPixmap:
        # The portal returns the whole desktop in device pixels. Map the
        # logical region into it using the overall desktop scale.
        desktop = ScreenCaptureService.virtual_geometry()
        if desktop.isEmpty():
            raise ScreenCaptureError("No monitor is available.")
        scale_x = image.width() / desktop.width()
        scale_y = image.height() / desktop.height()
        source = QRect(
            round((rect.x() - desktop.x()) * scale_x),
            round((rect.y() - desktop.y()) * scale_y),
            max(1, round(rect.width() * scale_x)),
            max(1, round(rect.height() * scale_y)),
        ).intersected(image.rect())
        if source.isEmpty():
            raise ScreenCaptureError("The capture area is outside the screenshot.")
        return QPixmap.fromImage(image.copy(source))


def default_backends() -> list[CaptureBackend]:
    """Capture methods to try, best first, for the current desktop."""

    if not is_wayland_session():
        return [QtGrabBackend()]
    backends: list[CaptureBackend] = []
    grim = shutil.which("grim")
    if grim:
        backends.append(GrimBackend(grim))
    try:
        backends.append(PortalBackend())
    except CaptureBackendUnavailable as exc:
        LOGGER.info("Screenshot portal unavailable: %s", exc)
    return backends


class ScreenCaptureService:
    """Capture pixels without opening or inspecting any application process."""

    def __init__(self, backends: list[CaptureBackend] | None = None) -> None:
        self._backends: list[CaptureBackend] | None = (
            list(backends) if backends is not None else None
        )
        self._unavailable_reasons: list[str] = []

    @property
    def backends(self) -> list[CaptureBackend]:
        if self._backends is None:
            self._backends = default_backends()
        return self._backends

    @property
    def backend_name(self) -> str:
        backends = self.backends
        return backends[0].name if backends else "none"

    def support_status(self) -> tuple[bool, str]:
        if self.backends:
            return True, f"Screen capture uses {self.backend_name}."
        detail = "; ".join(self._unavailable_reasons)
        return False, (
            "This Wayland desktop offers no screen capture method. Install 'grim' "
            "(Sway, Hyprland, niri, river) or xdg-desktop-portal for your desktop"
            + (f" ({detail})" if detail else "")
            + "."
        )

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
    def screen_for_rect(target: QRect) -> QScreen | None:
        for screen in QGuiApplication.screens():
            if screen.geometry().contains(target):
                return screen
        return None

    @classmethod
    def screen_for_region(cls, region: CaptureRegion) -> QScreen | None:
        return cls.screen_for_rect(region.to_qrect())

    def validate_region(self, region: CaptureRegion) -> None:
        if not region.is_valid:
            raise ScreenCaptureError("Select an area at least 32 × 16 pixels.")
        if self.screen_for_region(region) is None:
            raise ScreenCaptureError("The capture area must stay inside one monitor.")

    def capture(self, region: CaptureRegion) -> QPixmap:
        self.validate_region(region)
        return self._grab(region.to_qrect())

    def capture_screen(self, screen: QScreen) -> QPixmap:
        """Capture one whole monitor, e.g. as a frozen backdrop for selection."""

        return self._grab(QRect(screen.geometry()))

    def _grab(self, rect: QRect) -> QPixmap:
        while self.backends:
            backend = self.backends[0]
            try:
                return backend.grab(rect)
            except CaptureBackendUnavailable as exc:
                # This method cannot work on this desktop; use the next one.
                LOGGER.info("Screen capture via %s unavailable: %s", backend.name, exc)
                self._unavailable_reasons.append(f"{backend.name}: {exc}")
                self.backends.pop(0)
        raise CaptureBackendUnavailable(self.support_status()[1])

    @staticmethod
    def png_bytes_for_ocr(pixmap: QPixmap) -> bytes:
        """Create a larger grayscale PNG entirely in memory for OCR."""

        image = pixmap.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
        # OCR engines are substantially more reliable with dark text on a light
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
