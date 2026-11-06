"""Overlay windows for GNOME on Wayland, via XWayland.

GNOME does not implement wlr-layer-shell, and its Wayland clients cannot ask
to stay above other windows or appear on every workspace. GNOME still runs X11
applications through XWayland, though, and X11 lets a window bypass the window
manager ("override-redirect", as used by menus and tooltips). Mutter draws such
windows in its top-most layer, above fullscreen windows, and they are not tied
to any workspace. Click-through uses an empty X11 input shape, which Qt sets
for ``WindowTransparentForInput``.

Qt picks one display system per process, so on GNOME Wayland the whole app
runs under XWayland (``QT_QPA_PLATFORM=xcb``). This must be decided before the
QApplication exists; see :func:`prefer_xwayland_for_overlays`.

Set ``ISLE_COMPANION_X11_OVERLAY=0`` to disable this, or ``=1`` to use the
override-redirect overlay on other X11 desktops too.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

LOGGER = logging.getLogger(__name__)

_ENV = "ISLE_COMPANION_X11_OVERLAY"


def _env_choice() -> bool | None:
    value = os.environ.get(_ENV, "").strip().lower()
    if value in {"0", "off", "false", "no"}:
        return False
    if value in {"1", "on", "true", "yes"}:
        return True
    return None


def is_gnome_wayland_session() -> bool:
    desktops = {
        part.strip().lower()
        for part in os.environ.get("XDG_CURRENT_DESKTOP", "").split(":")
        if part.strip()
    }
    return (
        os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
        and bool(os.environ.get("WAYLAND_DISPLAY"))
        and bool(desktops & {"gnome", "gnome-classic", "gnome-flashback"})
    )


def prefer_xwayland_for_overlays() -> bool:
    """Choose XWayland on GNOME Wayland. Call before creating QApplication.

    Returns True when the platform was switched. A platform chosen explicitly
    by the user (``QT_QPA_PLATFORM``) is always respected.
    """

    if os.name == "nt" or _env_choice() is False:
        return False
    if os.environ.get("QT_QPA_PLATFORM"):
        return False
    if not is_gnome_wayland_session() or not os.environ.get("DISPLAY"):
        return False
    os.environ["QT_QPA_PLATFORM"] = "xcb"
    LOGGER.info("GNOME Wayland session: using XWayland for overlay windows")
    return True


def x11_overlay_active() -> bool:
    """True when overlay windows should bypass the window manager."""

    if os.name == "nt" or QGuiApplication.platformName().lower() != "xcb":
        return False
    choice = _env_choice()
    if choice is not None:
        return choice
    return is_gnome_wayland_session()


def overlay_window_flags(*, interactable: bool) -> Qt.WindowType:
    flags = (
        Qt.WindowType.Window
        | Qt.WindowType.X11BypassWindowManagerHint
        | Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.NoDropShadowWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
    )
    if not interactable:
        flags |= Qt.WindowType.WindowTransparentForInput
    return flags
