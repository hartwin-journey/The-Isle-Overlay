import copy
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.app_state import AppState
from core.coordinate_transform import load_calibration
from core.data_loader import LayerRepository
from core.settings import DEFAULT_SETTINGS
from core.wayland_layer_overlay import (
    WaylandLayerOverlay,
    layer_shell_candidate,
    layer_shell_disabled_by_env,
)
from ui.mini_map import MiniMapWindow


def test_layer_shell_is_not_used_without_a_wayland_qt_platform(monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-test")
    # Tests run on the offscreen platform, which never hosts an overlay.
    assert layer_shell_candidate() is False


def test_layer_shell_can_be_disabled_by_environment(monkeypatch):
    monkeypatch.setenv("ISLE_COMPANION_LAYER_SHELL", "0")
    assert layer_shell_disabled_by_env() is True
    assert layer_shell_candidate() is False
    monkeypatch.setenv("ISLE_COMPANION_LAYER_SHELL", "1")
    assert layer_shell_disabled_by_env() is False


def test_mini_map_falls_back_to_a_normal_window(monkeypatch):
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    state = AppState(copy.deepcopy(DEFAULT_SETTINGS))
    mini_map = MiniMapWindow(
        root / "assets" / "map" / "gateway.webp",
        load_calibration(root / "assets" / "map" / "calibration.json"),
        LayerRepository(root / "data"),
        state,
    )
    assert mini_map.layer_overlay is None
    assert WaylandLayerOverlay.create(mini_map) is None
    mini_map.set_interaction_enabled(True)
    assert mini_map.interaction_enabled is True
    mini_map.deleteLater()
    app.processEvents()
