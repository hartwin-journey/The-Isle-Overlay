"""Regression coverage for settings recovery and everyday map interactions."""

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QToolBar

from core.app_state import AppState
from core.coordinate_transform import load_calibration
from core.data_loader import LayerRepository
from core.overlay_interaction import ToggleInputMonitor
from core.settings import DEFAULT_SETTINGS, SettingsStore
from ui.main_window import MainWindow


@pytest.mark.parametrize("bad_value", [None, [], "invalid", float("inf"), float("nan")])
def test_invalid_settings_fields_preserve_other_preferences(tmp_path, bad_value):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({
        "overlay_size": bad_value,
        "layers": bad_value,
        "hotkeys": bad_value,
        "individual_migrations": bad_value,
        "overlay_shape": bad_value,
        "map_label_font_preset": bad_value,
        "automatic_tracking_region": {"width": bad_value},
        "overlay_opacity": 0.73,
    }), encoding="utf-8")
    store = SettingsStore(path)
    values = store.load()
    assert values["overlay_size"] == DEFAULT_SETTINGS["overlay_size"]
    assert values["layers"] == DEFAULT_SETTINGS["layers"]
    assert values["hotkeys"] == DEFAULT_SETTINGS["hotkeys"]
    assert values["individual_migrations"] == {}
    assert values["overlay_opacity"] == 0.73
    store.save()
    assert SettingsStore(path).load() == values


def test_toolbar_state_is_respected_by_next_edit_shortcut():
    app = QApplication.instance() or QApplication([])
    pressed = set()
    monitor = ToggleInputMonitor("M4", state_reader=lambda key: key in pressed)
    events = []
    monitor.toggled_changed.connect(events.append)
    monitor.sync_active(True)
    assert events == []  # Sync must not recursively emit a toggle.
    pressed.add(0x05)
    monitor.poll_now()
    assert events == [False]
    assert not monitor.active


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    store = SettingsStore(tmp_path / "settings.json")
    state = AppState(store.values)
    window = MainWindow(
        root, store, load_calibration(root / "map" / "calibration.json"),
        LayerRepository(root / "data"), state, windows_features=True,
    )
    window.show()
    app.processEvents()
    yield window
    window.close()
    window.deleteLater()
    app.processEvents()


def test_layer_shortcut_syncs_checkbox_without_extra_saves(window):
    events = []
    window.layer_panel.settings_modified.connect(lambda: events.append(True))
    window.toggle_breadcrumbs()
    assert not window.layer_panel.layer_checkboxes["breadcrumbs"].isChecked()
    assert not window.state.settings["layers"]["breadcrumbs"]
    assert events == []
    window.toggle_breadcrumbs()
    assert window.layer_panel.layer_checkboxes["breadcrumbs"].isChecked()


def test_hiding_full_map_does_not_change_layer_preference(window):
    window.hide()
    assert window.state.settings["layer_panel_visible"] is True
    window.show()
    window.toggle_layer_panel()
    assert window.state.settings["layer_panel_visible"] is False
    window.hide()
    window.show()
    assert window.layer_dock.isHidden()
    window.toggle_layer_panel()
    assert window.state.settings["layer_panel_visible"] is True


def test_windows_edit_fallback_and_tracking_off_feedback(window):
    toolbar = window.findChild(QToolBar, "mainToolbar")
    assert window.mini_map_edit_action in toolbar.actions()
    window.set_automatic_tracking_status(True, "Reading screen coordinates")
    window.set_automatic_tracking_status(False, "Automatic tracking: off")
    assert "Clipboard tracking ready" in window.clipboard_status.text()
    assert not window.automatic_tracking_action.isChecked()


def test_waypoint_actions_follow_active_destination(window):
    assert not window.save_waypoint_action.isEnabled()
    assert not window.remove_waypoint_action.isEnabled()
    window._place_waypoint(1000, 2000)
    assert window.save_waypoint_action.isEnabled()
    assert window.remove_waypoint_action.isEnabled()
    window.clear_waypoint()
    assert not window.save_waypoint_action.isEnabled()
    assert not window.remove_waypoint_action.isEnabled()


def test_horizontal_scroll_does_not_zoom_and_zoom_stays_in_bounds(window):
    canvas = window.map_canvas

    def wheel(x, y):
        event = QWheelEvent(
            QPointF(100, 100), QPointF(100, 100), QPoint(), QPoint(x, y),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase, False,
        )
        canvas.wheelEvent(event)

    original = canvas.transform().m11()
    wheel(120, 0)
    assert canvas.transform().m11() == original
    canvas.resetTransform()
    canvas.scale(19.9, 19.9)
    wheel(0, 120)
    assert canvas.transform().m11() == pytest.approx(20.0)
    canvas.resetTransform()
    canvas.scale(0.051, 0.051)
    wheel(0, -120)
    assert canvas.transform().m11() == pytest.approx(0.05)
