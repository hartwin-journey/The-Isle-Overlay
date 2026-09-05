import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGraphicsItem,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QGroupBox,
    QLabel,
    QTabWidget,
    QToolBar,
)

from core.app_state import AppState
from core.coordinate_transform import load_calibration
from core.data_loader import LayerRepository
from core.models import Position, Waypoint
from core.settings import DEFAULT_SETTINGS, SettingsStore
from core.screen_capture import CaptureRegion
from ui.main_window import MainWindow
from ui.mini_map import MINI_MAP_FOOTER_HEIGHT, MiniMapWindow
from ui.ocr_setup_window import OcrSetupDialog
from ui.settings_window import SettingsWindow


def test_full_and_mini_map_render_state(tmp_path):
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    settings["mini_map_show_poi_labels"] = True
    settings["poi_label_font_size_full"] = 17
    settings["poi_label_font_size_mini"] = 12
    settings["map_label_font_preset"] = "verdana_bold"
    settings["layer_opacity"]["locations"] = 0.42
    store = SettingsStore(tmp_path / "settings.json")
    store.values = settings
    calibration = load_calibration(root / "assets" / "map" / "calibration.json")
    repository = LayerRepository(root / "data")
    state = AppState(settings)

    full_map = MainWindow(root, store, calibration, repository, state)
    mini_map = MiniMapWindow(root / "assets" / "map" / "gateway.webp", calibration, repository, state)
    full_map.attach_mini_map(mini_map)
    state.update_position(Position(1000, 2000, 300, datetime.now(timezone.utc)))
    state.update_position(Position(2000, 3500, 305, datetime.now(timezone.utc)))
    state.set_waypoint(Waypoint("Test waypoint", 10000, 12000, 0))
    app.processEvents()

    assert full_map.coordinate_label.text().startswith("X 2,000.000")
    assert len(state.breadcrumbs) == 2
    assert full_map.map_canvas._groups["player"].childItems()
    assert full_map.map_canvas._groups["breadcrumbs"].childItems()
    assert full_map.map_canvas._groups["patrol_zones"].childItems()
    assert not full_map.map_canvas._groups["patrol_zones"].isVisible()
    assert len(full_map.map_canvas._groups["updrafts"].childItems()) == 42
    assert len(mini_map.map_canvas._groups["updrafts"].childItems()) == 42
    assert all(
        item.flags()
        & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
        for item in full_map.map_canvas._groups["updrafts"].childItems()
    )
    assert mini_map.map_canvas._groups["waypoint"].childItems()
    assert full_map.automatic_tracking_action.text() == "Automatic Tracking"
    assert not full_map.automatic_tracking_action.isChecked()
    assert full_map.automatic_tracking_action.menu() is not None
    assert full_map.automatic_tracking_setup_action.text() == "Set up capture area…"
    assert len(full_map.map_canvas._groups["waypoint_route"].childItems()) == 2
    assert len(mini_map.map_canvas._groups["waypoint_route"].childItems()) == 2
    full_labels = [
        item
        for item in full_map.map_canvas._groups["locations"].childItems()
        if isinstance(item, QGraphicsSimpleTextItem)
    ]
    mini_labels = [
        item
        for item in mini_map.map_canvas._groups["locations"].childItems()
        if isinstance(item, QGraphicsSimpleTextItem)
    ]
    assert full_labels and full_labels[0].font().pointSize() == 17
    assert mini_labels and mini_labels[0].font().pointSize() == 12
    assert full_labels[0].font().family() == "Verdana"
    assert full_labels[0].font().weight() == QFont.Weight.Bold
    assert full_labels[0].pen().style() != Qt.PenStyle.NoPen
    assert full_labels[0].flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
    assert full_map.map_canvas._groups["locations"].opacity() == 0.42
    assert mini_map.map_canvas._groups["locations"].opacity() == 0.42
    assert all(
        item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
        for item in full_map.map_canvas._groups["player"].childItems()
    )
    assert full_map.map_canvas._groups["breadcrumbs"].childItems()
    assert full_map.nearest_poi_label.text().startswith("Nearest POI:")
    assert " · " in full_map.nearest_poi_label.text()
    assert mini_map.nearest_poi_label.toolTip() == full_map.nearest_poi_label.text()
    assert mini_map.width() == settings["overlay_size"]
    assert mini_map.height() == settings["overlay_size"] + MINI_MAP_FOOTER_HEIGHT
    assert mini_map.map_canvas.size().width() == settings["overlay_size"]
    assert (
        mini_map.map_canvas.viewportUpdateMode()
        == QGraphicsView.ViewportUpdateMode.FullViewportUpdate
    )
    assert not mini_map.nearest_poi_label.isHidden()

    preset_expectations = {
        "segoe_semibold": ("Segoe UI", QFont.Weight.DemiBold),
        "verdana_bold": ("Verdana", QFont.Weight.Bold),
        "tahoma_bold": ("Tahoma", QFont.Weight.Bold),
        "arial_bold": ("Arial", QFont.Weight.Bold),
        "segoe_regular": ("Segoe UI", QFont.Weight.Normal),
    }
    for preset_id, (family, weight) in preset_expectations.items():
        state.settings["map_label_font_preset"] = preset_id
        state.settings_changed.emit()
        app.processEvents()
        rendered_label = next(
            item
            for item in full_map.map_canvas._groups["locations"].childItems()
            if isinstance(item, QGraphicsSimpleTextItem)
        )
        assert rendered_label.font().family() == family
        assert rendered_label.font().weight() == weight
        assert full_map.nearest_poi_label.font().family() == family
        assert mini_map.nearest_poi_label.font().family() == family

    for layer_name in (
        "water",
        "locations",
        "food",
        "ai",
        "salt_licks",
        "spawns",
        "custom_markers",
    ):
        state.settings["layers"][layer_name] = False
    state.layers_changed.emit()
    app.processEvents()
    assert full_map.nearest_poi_label.text() == "Nearest POI: none in visible layers"
    assert mini_map.nearest_poi_label.toolTip() == full_map.nearest_poi_label.text()
    state.settings["layers"]["locations"] = True
    state.layers_changed.emit()
    app.processEvents()
    assert full_map.nearest_poi_label.text() != "Nearest POI: none in visible layers"

    assert mini_map.control_strip.isHidden()
    assert mini_map.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert mini_map.windowFlags() & Qt.WindowType.WindowTransparentForInput
    mini_map.set_interaction_enabled(True)
    assert not mini_map.control_strip.isHidden()
    assert not mini_map.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert not mini_map.windowFlags() & Qt.WindowType.WindowTransparentForInput
    mini_map._toggle_shape()
    assert state.settings["overlay_shape"] == "circle"
    assert not mini_map.mask().isEmpty()
    assert mini_map.mask().contains(QPoint(mini_map.width() // 2, mini_map.width() // 2))
    assert not mini_map.mask().contains(QPoint(0, 0))
    assert mini_map.mask().contains(
        QPoint(mini_map.width() // 2, mini_map.map_canvas.height() + 10)
    )
    assert mini_map.windowFlags() & Qt.WindowType.NoDropShadowWindowHint
    mini_map._toggle_shape()
    assert state.settings["overlay_shape"] == "square"
    assert mini_map.mask().isEmpty()
    mini_map._toggle_shape()
    assert state.settings["overlay_shape"] == "circle"
    assert not mini_map.mask().isEmpty()
    mini_map._finish_resize(444)
    assert state.settings["overlay_size"] == 444
    assert mini_map.size().height() == 444 + MINI_MAP_FOOTER_HEIGHT
    assert mini_map.map_canvas.size().width() == 444
    assert json.loads(store.path.read_text(encoding="utf-8"))["overlay_size"] == 444
    mini_map._set_follow_player(False)
    assert not state.settings["player_centered_mode"]
    mini_map._set_follow_player(True)
    assert state.settings["player_centered_mode"]
    mini_map.set_interaction_enabled(False)
    assert mini_map.control_strip.isHidden()
    assert mini_map.windowFlags() & Qt.WindowType.WindowTransparentForInput

    automatic_events = []
    full_map.automatic_tracking_changed.connect(automatic_events.append)
    state.settings["automatic_tracking_region"] = {
        "x": 100,
        "y": 100,
        "width": 600,
        "height": 80,
    }
    full_map.automatic_tracking_action.trigger()
    assert state.settings["automatic_tracking_enabled"] is True
    assert automatic_events == [True]
    full_map.automatic_tracking_action.trigger()
    assert state.settings["automatic_tracking_enabled"] is False
    assert automatic_events == [True, False]

    full_map.deleteLater()
    mini_map.deleteLater()
    app.processEvents()


def test_clicking_active_waypoint_clears_it_and_route_tracks_player(tmp_path):
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    store = SettingsStore(tmp_path / "settings.json")
    store.values = settings
    calibration = load_calibration(root / "assets" / "map" / "calibration.json")
    repository = LayerRepository(root / "data")
    state = AppState(settings)
    window = MainWindow(root, store, calibration, repository, state)
    window.show()
    window.map_canvas.reset_view()
    app.processEvents()

    scene_center = window.map_canvas.sceneRect().center()
    waypoint_x, waypoint_y = calibration.pixel_to_world(
        scene_center.x(), scene_center.y()
    )
    player = Position(
        waypoint_x - 10_000,
        waypoint_y - 5_000,
        0,
        datetime.now(timezone.utc),
    )
    state.update_position(player)
    state.set_waypoint(Waypoint("Click to clear", waypoint_x, waypoint_y))
    app.processEvents()

    route_items = window.map_canvas._groups["waypoint_route"].childItems()
    assert len(route_items) == 2
    old_path = route_items[-1].path()

    state.update_position(
        Position(
            player.x - 5_000,
            player.y,
            0,
            datetime.now(timezone.utc),
        )
    )
    app.processEvents()
    new_path = window.map_canvas._groups["waypoint_route"].childItems()[-1].path()
    assert new_path != old_path

    waypoint_scene = QPointF(*calibration.world_to_pixel(waypoint_x, waypoint_y))
    waypoint_view = window.map_canvas.mapFromScene(waypoint_scene)
    QTest.mouseClick(
        window.map_canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=waypoint_view,
    )
    app.processEvents()

    assert state.active_waypoint is None
    assert not window.map_canvas._groups["waypoint_route"].childItems()
    window.close()
    window.deleteLater()
    app.processEvents()


def test_polished_settings_hide_local_data_and_consolidate_zone_intensity():
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    calibration = load_calibration(root / "assets" / "map" / "calibration.json")
    dialog = SettingsWindow(settings, calibration, root)

    group_titles = {group.title() for group in dialog.findChildren(QGroupBox)}
    assert "Local data" not in group_titles
    assert "Enabled layers" not in group_titles
    assert "Coordinate tracking" not in group_titles

    dialog._layer_opacity_sliders["zones"].setValue(50)
    font_index = dialog.map_label_font.findData("tahoma_bold")
    dialog.map_label_font.setCurrentIndex(font_index)
    dialog._accept_values()
    assert dialog.settings["layer_opacity"]["migrations"] == 0.21
    assert dialog.settings["layer_opacity"]["patrol_zones"] == 0.165
    assert dialog.settings["layer_opacity"]["sanctuaries"] == 0.3
    assert dialog.settings["map_label_font_preset"] == "tahoma_bold"
    dialog.deleteLater()
    app.processEvents()


def test_linux_ui_hides_windows_features_and_can_edit_mini_map(tmp_path):
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    store = SettingsStore(tmp_path / "settings.json")
    store.values = settings
    calibration = load_calibration(root / "assets" / "map" / "calibration.json")
    repository = LayerRepository(root / "data")
    state = AppState(settings)
    window = MainWindow(
        root,
        store,
        calibration,
        repository,
        state,
        windows_features=False,
    )
    mini_map = MiniMapWindow(
        root / "assets" / "map" / "gateway.webp",
        calibration,
        repository,
        state,
    )
    window.attach_mini_map(mini_map)

    toolbar = window.findChild(QToolBar, "mainToolbar")
    assert toolbar is not None
    assert window.mini_map_edit_action in toolbar.actions()
    assert window.automatic_tracking_action not in toolbar.actions()

    window.mini_map_edit_action.trigger()
    app.processEvents()
    assert mini_map.interaction_enabled is True
    assert window.mini_map_edit_action.isChecked()
    window.mini_map_edit_action.trigger()
    app.processEvents()
    assert mini_map.interaction_enabled is False

    dialog = SettingsWindow(
        settings,
        calibration,
        root,
        windows_features=False,
    )
    tabs = dialog.findChild(QTabWidget)
    assert tabs is not None
    assert "Shortcuts" in [tabs.tabText(index) for index in range(tabs.count())]
    assert dialog.interaction_hold_key.text() == "M4"
    assert dialog._hotkeys == {}
    dialog.interaction_hold_key._finish_capture("Ctrl+Shift+I")
    dialog._accept_values()
    assert dialog.settings["overlay_interaction_hold_key"] == "Ctrl+Shift+I"
    assert any(
        "CLIPBOARD ONLY" in label.text()
        for label in dialog.findChildren(QLabel)
    )

    dialog.deleteLater()
    mini_map.close()
    window.close()
    mini_map.deleteLater()
    window.deleteLater()
    app.processEvents()


def test_automatic_tracking_setup_is_modeless_and_owned_by_toolbar(tmp_path):
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    store = SettingsStore(tmp_path / "settings.json")
    store.values = settings
    calibration = load_calibration(root / "assets" / "map" / "calibration.json")
    repository = LayerRepository(root / "data")
    state = AppState(settings)
    window = MainWindow(root, store, calibration, repository, state)
    enabled_events: list[bool] = []
    window.automatic_tracking_changed.connect(enabled_events.append)
    window.show()

    window.automatic_tracking_setup_action.trigger()
    app.processEvents()

    setup = window._ocr_setup_dialog
    assert setup is not None
    assert setup.isVisible()
    assert setup.windowModality() == Qt.WindowModality.NonModal
    assert not window.automatic_tracking_action.isChecked()

    region = CaptureRegion(x=10, y=10, width=320, height=64)
    setup.x_field.setValue(region.x)
    setup.y_field.setValue(region.y)
    setup.width_field.setValue(region.width)
    setup.height_field.setValue(region.height)
    setup._accept_region()
    app.processEvents()

    assert state.settings["automatic_tracking_region"] == region.to_dict()
    assert state.settings["automatic_tracking_enabled"] is False
    assert not window.automatic_tracking_action.isChecked()
    assert window.automatic_tracking_setup_action.text() == "Change capture area…"
    assert enabled_events == []

    window.automatic_tracking_action.trigger()
    app.processEvents()

    assert state.settings["automatic_tracking_enabled"] is True
    assert window.automatic_tracking_action.isChecked()
    assert enabled_events == [True]
    window.close()
    window.deleteLater()
    app.processEvents()


def test_ocr_setup_keeps_modal_session_alive_while_selecting_screen_area():
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    dialog = OcrSetupDialog(copy.deepcopy(DEFAULT_SETTINGS), root)
    observations: dict[str, bool] = {}

    def begin_selection() -> None:
        dialog._hide_companion_windows()
        observations["still_visible"] = dialog.isVisible()

        def finish_selection() -> None:
            dialog._restore_companion_windows()
            dialog.accept()

        QTimer.singleShot(10, finish_selection)

    QTimer.singleShot(0, begin_selection)
    assert dialog.exec() == QDialog.DialogCode.Accepted
    assert observations == {"still_visible": True}
    dialog.deleteLater()
    app.processEvents()


def test_ocr_setup_retains_a_completed_screen_selection():
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    dialog = OcrSetupDialog(copy.deepcopy(DEFAULT_SETTINGS), root)
    selected = CaptureRegion(x=140, y=220, width=640, height=72)
    dialog._capture_hidden = lambda region: None  # type: ignore[method-assign]

    dialog._selection_finished(selected)

    assert dialog.region == selected
    assert dialog.current_region() == selected
    dialog.reject()
    dialog.deleteLater()
    app.processEvents()
