"""Hook-free Windows interaction-key polling and overlay input-style helpers."""

from __future__ import annotations

import ctypes
import logging
import os
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from core.hotkeys import parse_hold_binding

LOGGER = logging.getLogger(__name__)

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020


def overlay_extended_style(current_style: int, interactable: bool) -> int:
    """Return a no-activate style that is click-through unless interactable."""

    style = current_style | WS_EX_LAYERED | WS_EX_NOACTIVATE
    if interactable:
        return style & ~WS_EX_TRANSPARENT
    return style | WS_EX_TRANSPARENT


def apply_windows_overlay_input_style(window_id: int, interactable: bool) -> bool:
    """Apply click-through/no-activate flags to one ordinary top-level window."""

    if os.name != "nt" or not window_id:
        return False
    try:
        user32 = ctypes.windll.user32
        get_style = user32.GetWindowLongPtrW
        set_style = user32.SetWindowLongPtrW
        get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
        get_style.restype = ctypes.c_ssize_t
        set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        set_style.restype = ctypes.c_ssize_t
        set_pos = user32.SetWindowPos
        set_pos.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        set_pos.restype = ctypes.c_int
        handle = ctypes.c_void_p(window_id)
        current = int(get_style(handle, GWL_EXSTYLE))
        updated = overlay_extended_style(current, interactable)
        set_style(handle, GWL_EXSTYLE, updated)
        set_pos(
            handle,
            ctypes.c_void_p(0),
            0,
            0,
            0,
            0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )
        return True
    except (AttributeError, OSError) as exc:
        LOGGER.error("Could not apply Mini Map input style: %s", exc)
        return False


class ToggleInputMonitor(QObject):
    """Poll a physical key and toggle interaction on each press edge.

    ``GetAsyncKeyState`` is used only to observe the configured key.  The
    binding is never registered, hooked, consumed, or forwarded, so a mouse
    button such as M4 remains available to the game and other applications.
    """

    toggled_changed = Signal(bool)
    # Kept as a compatibility signal for callers from the previous hold-mode
    # implementation.  It now reports the persistent toggle state, not the
    # instantaneous physical key state.
    held_changed = Signal(bool)
    binding_error = Signal(str)

    def __init__(
        self,
        binding: str,
        *,
        state_reader: Callable[[int], bool] | None = None,
        interval_ms: int = 25,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._state_reader = state_reader or self._read_windows_key
        self._keys: tuple[int, ...] = ()
        self._active = False
        self._physical_pressed = False
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.poll_now)
        self.set_binding(binding)

    @staticmethod
    def _read_windows_key(virtual_key: int) -> bool:
        if os.name != "nt":
            return False
        return bool(ctypes.windll.user32.GetAsyncKeyState(virtual_key) & 0x8000)

    def set_binding(self, binding: str) -> bool:
        try:
            keys = parse_hold_binding(binding)
        except ValueError as exc:
            LOGGER.error("Invalid overlay interaction binding %r: %s", binding, exc)
            self.binding_error.emit(str(exc))
            return False
        self._keys = keys
        # Establish a baseline for the new binding.  Changing settings while
        # the key is already down must not create a synthetic toggle.
        try:
            self._physical_pressed = self._read_combination()
        except OSError as exc:
            LOGGER.error("Could not read overlay interaction binding state: %s", exc)
            self._physical_pressed = False
        return True

    def start(self) -> None:
        # Ignore a key that was already down before monitoring started.  A
        # subsequent release and press is required to toggle the overlay.
        try:
            self._physical_pressed = self._read_combination()
        except OSError as exc:
            LOGGER.error("Could not read overlay interaction binding state: %s", exc)
            self._physical_pressed = False
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._physical_pressed = False
        if self._active:
            self._active = False
            self._emit_state(False)

    def sync_active(self, active: bool) -> None:
        """Keep the next shortcut toggle aligned with toolbar changes."""

        self._active = bool(active)

    def _read_combination(self) -> bool:
        return bool(self._keys) and all(self._state_reader(key) for key in self._keys)

    def _emit_state(self, active: bool) -> None:
        self.toggled_changed.emit(active)
        self.held_changed.emit(active)

    def poll_now(self) -> None:
        try:
            pressed = self._read_combination()
        except OSError as exc:
            LOGGER.error("Could not read overlay interaction binding state: %s", exc)
            pressed = False
        if pressed and not self._physical_pressed:
            self._active = not self._active
            self._emit_state(self._active)
        self._physical_pressed = pressed

    @property
    def active(self) -> bool:
        return self._active

    @property
    def held(self) -> bool:
        """Compatibility alias for the prior monitor API."""

        return self._active


# Source compatibility for integrations that imported the old class name.
HoldInputMonitor = ToggleInputMonitor
