import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from core import x11_overlay
from core.x11_overlay import (
    is_gnome_wayland_session,
    overlay_window_flags,
    prefer_xwayland_for_overlays,
    x11_overlay_active,
)

GNOME = {
    "XDG_SESSION_TYPE": "wayland",
    "WAYLAND_DISPLAY": "wayland-0",
    "XDG_CURRENT_DESKTOP": "ubuntu:GNOME",
    "DISPLAY": ":0",
}


@pytest.fixture
def env(monkeypatch):
    for key in (*GNOME, "QT_QPA_PLATFORM", "ISLE_COMPANION_X11_OVERLAY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(x11_overlay.os, "name", "posix")
    return monkeypatch


def _set(monkeypatch, values):
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_detects_gnome_wayland_including_ubuntu(env):
    _set(env, GNOME)
    assert is_gnome_wayland_session() is True
    env.setenv("XDG_CURRENT_DESKTOP", "KDE")
    assert is_gnome_wayland_session() is False
    env.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    env.setenv("XDG_SESSION_TYPE", "x11")
    assert is_gnome_wayland_session() is False


def test_switches_to_xwayland_only_on_gnome_wayland(env):
    _set(env, GNOME)
    assert prefer_xwayland_for_overlays() is True
    assert os.environ["QT_QPA_PLATFORM"] == "xcb"


def test_respects_explicit_platform_and_opt_out(env):
    _set(env, GNOME)
    env.setenv("QT_QPA_PLATFORM", "wayland")
    assert prefer_xwayland_for_overlays() is False
    assert os.environ["QT_QPA_PLATFORM"] == "wayland"
    env.delenv("QT_QPA_PLATFORM")
    env.setenv("ISLE_COMPANION_X11_OVERLAY", "0")
    assert prefer_xwayland_for_overlays() is False
    assert "QT_QPA_PLATFORM" not in os.environ


def test_needs_xwayland_to_switch(env):
    _set(env, GNOME)
    env.delenv("DISPLAY")
    assert prefer_xwayland_for_overlays() is False


def test_overlay_inactive_off_x11():
    QApplication.instance() or QApplication([])
    assert x11_overlay_active() is False


def test_overlay_flags_bypass_window_manager_and_toggle_click_through():
    passive = overlay_window_flags(interactable=False)
    active = overlay_window_flags(interactable=True)
    assert passive & Qt.WindowType.X11BypassWindowManagerHint
    assert passive & Qt.WindowType.WindowTransparentForInput
    assert not active & Qt.WindowType.WindowTransparentForInput
