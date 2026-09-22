import os
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core import linux_overlay_interaction, overlay_interaction
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


def test_windows_overlay_style_helper_applies_native_window_flags(monkeypatch):
    class FakeFunction:
        def __init__(self, result):
            self.result = result
            self.calls = []

        def __call__(self, *args):
            self.calls.append(args)
            return self.result

    get_style = FakeFunction(0)
    set_style = FakeFunction(1)
    set_position = FakeFunction(1)
    user32 = SimpleNamespace(
        GetWindowLongPtrW=get_style,
        SetWindowLongPtrW=set_style,
        SetWindowPos=set_position,
    )
    monkeypatch.setattr(overlay_interaction.os, "name", "nt")
    monkeypatch.setattr(
        overlay_interaction.ctypes,
        "windll",
        SimpleNamespace(user32=user32),
        raising=False,
    )

    assert overlay_interaction.apply_windows_overlay_input_style(123, False)
    assert set_style.calls[0][2] & WS_EX_TRANSPARENT
    assert set_position.calls[0][-1] & overlay_interaction.SWP_FRAMECHANGED


def test_toggle_monitor_handles_invalid_bindings_and_stops_active_state():
    QApplication.instance() or QApplication([])
    events = []
    errors = []
    monitor = ToggleInputMonitor("M4", state_reader=lambda _key: False)
    monitor.toggled_changed.connect(events.append)
    monitor.binding_error.connect(errors.append)

    assert not monitor.set_binding("Ctrl+Shift")
    monitor.sync_active(True)
    monitor.stop()

    assert errors
    assert events == [False]
    assert not monitor.active
    assert monitor.held is False


def test_linux_monitor_starts_and_stops_non_consuming_listeners(monkeypatch):
    class FakeListener:
        def __init__(self, **callbacks):
            self.callbacks = callbacks
            self.started = False
            self.stopped = False

        def start(self):
            self.started = True

        def wait(self):
            return None

        def stop(self):
            self.stopped = True

    keyboard = SimpleNamespace(Listener=FakeListener)
    mouse = SimpleNamespace(Listener=FakeListener)
    monkeypatch.setattr(linux_overlay_interaction.os, "name", "posix")
    monkeypatch.setitem(sys.modules, "pynput", SimpleNamespace(keyboard=keyboard, mouse=mouse))
    monitor = LinuxToggleInputMonitor("M4")

    monitor.start()

    assert monitor.available
    assert all(listener.started for listener in monitor._listeners)
    listeners = list(monitor._listeners)
    monitor.stop()
    assert all(listener.stopped for listener in listeners)
    assert not monitor.available
