"""User-level Windows global hotkeys implemented with RegisterHotKey."""

from __future__ import annotations

import ctypes
import logging
import os
from ctypes import wintypes
from typing import Any

from PySide6.QtCore import QThread, Signal

LOGGER = logging.getLogger(__name__)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

SPECIAL_KEYS = {
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "HOME": 0x24,
    "END": 0x23,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
    "SPACE": 0x20,
}

HOLD_KEY_CODES = {
    "CTRL": 0x11,
    "CONTROL": 0x11,
    "SHIFT": 0x10,
    "ALT": 0x12,
    "WIN": 0x5B,
    "WINDOWS": 0x5B,
    "M4": 0x05,
    "XBUTTON1": 0x05,
    "M5": 0x06,
    "XBUTTON2": 0x06,
}


def _virtual_key_for_name(key_name: str) -> int:
    if len(key_name) == 1 and key_name.isalnum():
        return ord(key_name)
    if key_name.startswith("F") and key_name[1:].isdigit() and 1 <= int(key_name[1:]) <= 24:
        return 0x70 + int(key_name[1:]) - 1
    if key_name in {"M4", "XBUTTON1", "M5", "XBUTTON2"}:
        return HOLD_KEY_CODES[key_name]
    try:
        return SPECIAL_KEYS[key_name]
    except KeyError as exc:
        raise ValueError(f"unsupported hotkey key: {key_name}") from exc


def parse_hotkey(value: str) -> tuple[int, int]:
    parts = [part.strip().upper() for part in value.split("+") if part.strip()]
    modifiers = MOD_NOREPEAT
    key_name: str | None = None
    for part in parts:
        if part in {"CTRL", "CONTROL"}:
            modifiers |= MOD_CONTROL
        elif part == "SHIFT":
            modifiers |= MOD_SHIFT
        elif part == "ALT":
            modifiers |= MOD_ALT
        elif part in {"WIN", "WINDOWS"}:
            modifiers |= MOD_WIN
        elif key_name is None:
            key_name = part
        else:
            raise ValueError("hotkey must contain exactly one non-modifier key")
    if key_name is None:
        raise ValueError("hotkey has no key")
    virtual_key = _virtual_key_for_name(key_name)
    return modifiers, virtual_key


def parse_binding_names(value: str) -> tuple[str, ...]:
    """Return canonical names for a physical interaction binding."""

    aliases = {"CONTROL": "CTRL", "WINDOWS": "WIN", "XBUTTON1": "M4", "XBUTTON2": "M5"}
    parts = [part.strip().upper() for part in value.split("+") if part.strip()]
    if not parts:
        raise ValueError("hold binding has no key")
    names: list[str] = []
    primary_keys = 0
    modifiers = {"CTRL", "SHIFT", "ALT", "WIN"}
    for part in parts:
        name = aliases.get(part, part)
        if name not in modifiers:
            _virtual_key_for_name(name)
            primary_keys += 1
        if name not in names:
            names.append(name)
    if primary_keys != 1:
        raise ValueError("hold binding must contain exactly one non-modifier key")
    return tuple(names)


def parse_hold_binding(value: str) -> tuple[int, ...]:
    """Parse a physical interaction binding without registering or consuming it.

    The name is retained for settings/source compatibility; the monitor uses
    the parsed keys as a press-to-toggle binding rather than a hold binding.
    """

    names = parse_binding_names(value)
    return tuple(
        HOLD_KEY_CODES[name] if name in HOLD_KEY_CODES else _virtual_key_for_name(name)
        for name in names
    )


class GlobalHotkeyManager(QThread):
    """Register hotkeys in a dedicated message-loop thread on Windows."""

    activated = Signal(str)
    registration_failed = Signal(str, str)

    def __init__(self, hotkeys: dict[str, str]) -> None:
        super().__init__()
        self.hotkeys = dict(hotkeys)
        self._thread_id: int | None = None

    def run(self) -> None:
        if os.name != "nt":
            LOGGER.warning("Global hotkeys are only available on Windows")
            return
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = int(kernel32.GetCurrentThreadId())
        registered: dict[int, str] = {}
        for identifier, (action, shortcut) in enumerate(self.hotkeys.items(), start=1):
            try:
                modifiers, virtual_key = parse_hotkey(shortcut)
            except ValueError as exc:
                LOGGER.error("Invalid hotkey configuration for %s: %s", action, exc)
                self.registration_failed.emit(action, str(exc))
                continue
            if user32.RegisterHotKey(None, identifier, modifiers, virtual_key):
                registered[identifier] = action
            else:
                reason = "shortcut is unavailable or already registered"
                LOGGER.error("Could not register hotkey %s (%s)", action, shortcut)
                self.registration_failed.emit(action, reason)

        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            if message.message == WM_HOTKEY:
                action = registered.get(int(message.wParam))
                if action:
                    self.activated.emit(action)
        for identifier in registered:
            user32.UnregisterHotKey(None, identifier)

    def stop(self) -> None:
        if os.name == "nt" and self._thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self.wait(1500)
