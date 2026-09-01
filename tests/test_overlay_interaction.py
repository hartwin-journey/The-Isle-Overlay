from types import SimpleNamespace

from core.linux_overlay_interaction import LinuxToggleInputMonitor
from core.overlay_interaction import (
    ToggleInputMonitor,
    WS_EX_LAYERED,
    WS_EX_NOACTIVATE,
    WS_EX_TRANSPARENT,
    overlay_extended_style,
)


def test_overlay_style_is_click_through_only_when_not_interactable():
    locked = overlay_extended_style(0, interactable=False)
    assert locked & WS_EX_LAYERED
    assert locked & WS_EX_NOACTIVATE
    assert locked & WS_EX_TRANSPARENT

    interactive = overlay_extended_style(locked, interactable=True)
    assert interactive & WS_EX_LAYERED
    assert interactive & WS_EX_NOACTIVATE
    assert not interactive & WS_EX_TRANSPARENT


def test_toggle_monitor_emits_once_per_press_edge():
    pressed: set[int] = set()
    events: list[bool] = []
    monitor = ToggleInputMonitor("Ctrl+M4", state_reader=lambda key: key in pressed)
    monitor.toggled_changed.connect(events.append)

    monitor.poll_now()
    pressed.add(0x11)
    monitor.poll_now()
    pressed.add(0x05)
    monitor.poll_now()
    monitor.poll_now()
    pressed.remove(0x05)
    monitor.poll_now()
    pressed.add(0x05)
    monitor.poll_now()

    assert events == [True, False]
    assert monitor.active is False


def test_linux_toggle_monitor_observes_binding_without_grabbing():
    events: list[bool] = []
    monitor = LinuxToggleInputMonitor("Ctrl+M4")
    monitor.toggled_changed.connect(events.append)
    ctrl = SimpleNamespace(name="ctrl_l", char=None)
    side_button = SimpleNamespace(name="x1")

    monitor._on_key_press(ctrl)
    monitor._on_click(0, 0, side_button, True)
    monitor._on_click(0, 0, side_button, True)
    monitor._on_click(0, 0, side_button, False)
    monitor._on_click(0, 0, side_button, True)

    assert events == [True, False]
    monitor.sync_active(True)
    assert monitor.active is True
