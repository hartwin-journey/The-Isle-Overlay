"""Non-consuming Mini Map interaction binding for Linux desktops."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from PySide6.QtCore import QObject, Signal

from core.hotkeys import parse_binding_names

LOGGER = logging.getLogger(__name__)


class LinuxToggleInputMonitor(QObject):
    """Observe a Linux keyboard/mouse binding without grabbing its input.

    pynput uses X11/XWayland's normal observation facilities, so the configured
    input is still delivered to the game. Native Wayland compositors may deny
    global input observation; the Full Map edit button remains the fallback.
    """

    toggled_changed = Signal(bool)
    binding_error = Signal(str)

    def __init__(self, binding: str, *, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._required: tuple[str, ...] = ()
        self._pressed: set[str] = set()
        self._physical_pressed = False
        self._active = False
        self._listeners: list[Any] = []
        self._lock = threading.Lock()
        self.set_binding(binding)

    def set_binding(self, binding: str) -> bool:
        try:
            required = parse_binding_names(binding)
        except ValueError as exc:
            LOGGER.error("Invalid Linux overlay interaction binding %r: %s", binding, exc)
            self.binding_error.emit(str(exc))
            return False
        with self._lock:
            self._required = required
            self._pressed.clear()
            self._physical_pressed = False
        return True

    @staticmethod
    def _key_name(key: Any) -> str | None:
        character = getattr(key, "char", None)
        if character and len(character) == 1 and character.isalnum():
            return character.upper()
        name = str(getattr(key, "name", "")).upper()
        normalized = name.replace("_", "")
        aliases = {
            "CTRL": "CTRL",
            "CTRLL": "CTRL",
            "CTRLR": "CTRL",
            "SHIFT": "SHIFT",
            "SHIFTL": "SHIFT",
            "SHIFTR": "SHIFT",
            "ALT": "ALT",
            "ALTL": "ALT",
            "ALTR": "ALT",
            "ALTGR": "ALT",
            "CMD": "WIN",
            "CMDL": "WIN",
            "CMDR": "WIN",
            "PAGEUP": "PAGEUP",
            "PAGEDOWN": "PAGEDOWN",
            "SPACE": "SPACE",
            "HOME": "HOME",
            "END": "END",
            "INSERT": "INSERT",
            "DELETE": "DELETE",
        }
        if normalized in aliases:
            return aliases[normalized]
        if normalized.startswith("F") and normalized[1:].isdigit():
            return normalized
        return None

    @staticmethod
    def _button_name(button: Any) -> str | None:
        name = str(getattr(button, "name", "")).lower().replace("_", "")
        if name in {"x1", "button8", "back"}:
            return "M4"
        if name in {"x2", "button9", "forward"}:
            return "M5"
        return None

    def _set_pressed(self, name: str | None, pressed: bool) -> None:
        if name is None:
            return
        emit_state: bool | None = None
        with self._lock:
            if pressed:
                self._pressed.add(name)
            else:
                self._pressed.discard(name)
            binding_pressed = bool(self._required) and all(
                required in self._pressed for required in self._required
            )
            if binding_pressed and not self._physical_pressed:
                self._active = not self._active
                emit_state = self._active
            self._physical_pressed = binding_pressed
        if emit_state is not None:
            self.toggled_changed.emit(emit_state)

    def _on_key_press(self, key: Any) -> None:
        self._set_pressed(self._key_name(key), True)

    def _on_key_release(self, key: Any) -> None:
        self._set_pressed(self._key_name(key), False)

    def _on_click(self, _x: int, _y: int, button: Any, pressed: bool) -> None:
        self._set_pressed(self._button_name(button), bool(pressed))

    def start(self) -> None:
        if os.name == "nt" or self._listeners:
            return
        listeners: list[Any] = []
        try:
            from pynput import keyboard, mouse

            listeners = [
                keyboard.Listener(
                    on_press=self._on_key_press,
                    on_release=self._on_key_release,
                ),
                mouse.Listener(on_click=self._on_click),
            ]
            for listener in listeners:
                listener.start()
                listener.wait()
            self._listeners = listeners
        except (ImportError, OSError, RuntimeError) as exc:
            for listener in listeners:
                try:
                    listener.stop()
                except (OSError, RuntimeError):
                    pass
            reason = f"Linux desktop input access is unavailable ({exc})"
            LOGGER.warning(reason)
            self.binding_error.emit(reason)

    def stop(self) -> None:
        listeners, self._listeners = self._listeners, []
        for listener in listeners:
            try:
                listener.stop()
            except (OSError, RuntimeError):
                pass
        with self._lock:
            self._pressed.clear()
            self._physical_pressed = False

    def sync_active(self, active: bool) -> None:
        """Keep toolbar changes and shortcut toggles on the same state edge."""

        with self._lock:
            self._active = bool(active)

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def available(self) -> bool:
        return bool(self._listeners)
