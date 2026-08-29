import pytest

from core.hotkeys import (
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    parse_hold_binding,
    parse_hotkey,
)


def test_default_letter_hotkey():
    modifiers, key = parse_hotkey("Ctrl+Shift+M")
    assert modifiers & MOD_CONTROL
    assert modifiers & MOD_SHIFT
    assert modifiers & MOD_NOREPEAT
    assert key == ord("M")


def test_page_up_hotkey():
    _, key = parse_hotkey("Ctrl+Shift+PageUp")
    assert key == 0x21


def test_mouse_and_keyboard_interaction_bindings():
    assert parse_hold_binding("M4") == (0x05,)
    assert parse_hold_binding("M5") == (0x06,)
    assert parse_hold_binding("Ctrl+Shift+I") == (0x11, 0x10, ord("I"))


@pytest.mark.parametrize("value", ["Ctrl+Shift", "Ctrl+A+B", "Ctrl+MagicKey"])
def test_invalid_hotkey(value):
    with pytest.raises(ValueError):
        parse_hotkey(value)


@pytest.mark.parametrize("value", ["", "Ctrl+Shift", "M4+M5", "Ctrl+A+B"])
def test_invalid_hold_binding(value):
    with pytest.raises(ValueError):
        parse_hold_binding(value)
