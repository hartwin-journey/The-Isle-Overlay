"""Primary Full Map control interface."""

from __future__ import annotations

from datetime import timezone
import os
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.app_state import AppState
from core.coordinate_transform import MapCalibration, save_calibration
from core.data_loader import LayerRepository
from core.models import Position, Waypoint
from core.navigation import (
    cardinal_direction,
    format_distance,
    heading_degrees,
    nearest_named_poi,
    planar_distance,
)
from core.settings import SettingsStore
from core.screen_capture import CaptureRegion
from ui.layer_panel import LayerPanel
from ui.map_canvas import MapCanvas
from ui.map_fonts import build_map_label_font
from ui.mini_map import MiniMapWindow
from ui.how_to_use_window import HowToUseDialog
from ui.ocr_setup_window import OcrSetupDialog
from ui.settings_window import SettingsWindow


class MainWindow(QMainWindow):
    hotkeys_changed = Signal()
    automatic_tracking_changed = Signal(bool)
    exit_requested = Signal()

    def __init__(
        self,
        project_root: Path,
        settings_store: SettingsStore,
        calibration: MapCalibration,
        repository: LayerRepository,
        state: AppState,
        *,
        windows_features: bool | None = None,
    ) -> None:
        super().__init__()
        self.project_root = project_root
        self.settings_store = settings_store
        self.calibration_path = project_root / "assets" / "map" / "calibration.json"
        self.calibration = calibration
        self.repository = repository
        self.state = state
        self.windows_features = (
            os.name == "nt" if windows_features is None else bool(windows_features)
        )
        self.tray_available = False
        self.mini_map: MiniMapWindow | None = None
        self._ocr_setup_dialog: OcrSetupDialog | None = None
        self._enable_automatic_after_setup = False

        self.setWindowTitle("The Isle Companion — Full Map")
        self.resize(1280, 820)
        self.setMinimumSize(820, 560)
        self._build_toolbar()
        self._build_central_widget()
        self._build_layer_dock()
        self._build_status_bar()

        state.position_changed.connect(self._on_position_changed)
        state.waypoint_changed.connect(self._update_navigation_labels)
        state.layers_changed.connect(self._update_nearest_poi)
        state.settings_changed.connect(self._on_settings_changed)
        QTimer.singleShot(0, self.map_canvas.reset_view)

    def attach_mini_map(self, mini_map: MiniMapWindow) -> None:
        self.mini_map = mini_map
        mini_map.waypoint_requested.connect(self._place_waypoint)
        mini_map.waypoint_clear_requested.connect(self.clear_waypoint)
        mini_map.settings_modified.connect(self.settings_store.save)
        mini_map.interaction_changed.connect(self._sync_mini_map_edit_action)
        mini_map.set_nearest_poi_text(self.nearest_poi_label.text())
        self._sync_mini_map_edit_action(mini_map.interaction_enabled)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Map controls")
        toolbar.setMovable(False)
        toolbar.setObjectName("mainToolbar")
        self.addToolBar(toolbar)

        def add_action(label: str, callback: object) -> QAction:
            action = QAction(label, self)
            action.triggered.connect(callback)  # type: ignore[arg-type]
            toolbar.addAction(action)
            return action

        add_action("Layers", self.toggle_layer_panel)
        add_action("Mini Map", self.toggle_mini_map)
        self.mini_map_edit_action = QAction("Edit Mini Map", self)
        self.mini_map_edit_action.setCheckable(True)
        self.mini_map_edit_action.setToolTip(
            "Toggle the Mini Map between click-through and mouse editing"
        )
        self.mini_map_edit_action.triggered.connect(
            self._set_mini_map_interaction
        )
        if not self.windows_features:
            toolbar.addAction(self.mini_map_edit_action)
        self.automatic_tracking_action = QAction("Automatic Tracking", self)
        self.automatic_tracking_action.setCheckable(True)
        self.automatic_tracking_action.setChecked(
            bool(self.state.settings["automatic_tracking_enabled"])
        )
        self.automatic_tracking_action.setToolTip(
            "Read coordinates from a selected screen area using local Windows OCR"
        )
        self.automatic_tracking_action.triggered.connect(
            self._automatic_tracking_toggled
        )
        automatic_menu = QMenu(self)
        self.automatic_tracking_setup_action = automatic_menu.addAction(
            "Set up capture area…"
        )
        self.automatic_tracking_setup_action.triggered.connect(
            self.open_automatic_tracking_setup
        )
        self.automatic_tracking_action.setMenu(automatic_menu)
        if self.windows_features:
            toolbar.addAction(self.automatic_tracking_action)
        automatic_button = toolbar.widgetForAction(self.automatic_tracking_action)
        if isinstance(automatic_button, QToolButton):
            automatic_button.setPopupMode(
                QToolButton.ToolButtonPopupMode.MenuButtonPopup
            )
        self._refresh_automatic_tracking_control()
        toolbar.addSeparator()
        add_action("Fit", self._fit_map)
        add_action("Center Player", self.recenter_player)
        add_action("Clear Trail", self.clear_breadcrumbs)

        waypoint_button = QToolButton()
        waypoint_button.setText("Waypoint")
        waypoint_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        waypoint_menu = QMenu(waypoint_button)
        save_waypoint = waypoint_menu.addAction("Save active waypoint")
        save_waypoint.triggered.connect(self.save_waypoint)
        remove_waypoint = waypoint_menu.addAction("Remove active waypoint")
        remove_waypoint.triggered.connect(self.clear_waypoint)
        waypoint_button.setMenu(waypoint_menu)
        toolbar.addWidget(waypoint_button)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        add_action("How to use", self.open_how_to_use)
        add_action("Settings", self.open_settings)

    def _build_central_widget(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.map_canvas = MapCanvas(
            self.project_root / "assets" / "map" / "gateway.webp",
            self.calibration,
            self.repository,
            self.state,
        )
        self.map_canvas.waypoint_requested.connect(self._place_waypoint)
        self.map_canvas.waypoint_clear_requested.connect(self.clear_waypoint)
        layout.addWidget(self.map_canvas, 1)

        nearest_bar = QWidget()
        nearest_bar.setObjectName("nearestPoiBar")
        nearest_layout = QHBoxLayout(nearest_bar)
        nearest_layout.setContentsMargins(12, 6, 12, 6)
        self.nearest_poi_label = QLabel("Nearest POI: copy your coordinates to get started")
        self.nearest_poi_label.setObjectName("nearestPoiLabel")
        self.nearest_poi_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nearest_layout.addWidget(self.nearest_poi_label)
        layout.addWidget(nearest_bar)

        info_bar = QWidget()
        info_bar.setStyleSheet("background: #101c24; border-top: 1px solid #2c414e;")
        info_layout = QHBoxLayout(info_bar)
        info_layout.setContentsMargins(12, 8, 12, 8)
        self.coordinate_label = QLabel("X —    Y —    Z —")
        self.previous_label = QLabel("Previous: —")
        self.heading_label = QLabel("Heading: —")
        self.distance_label = QLabel("Waypoint: —")
        for label in (self.coordinate_label, self.previous_label, self.heading_label, self.distance_label):
            label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            info_layout.addWidget(label)
        layout.addWidget(info_bar)
        self.setCentralWidget(container)
        self._apply_map_label_font()

    def _build_layer_dock(self) -> None:
        self.layer_dock = QDockWidget("Map Layers", self)
        self.layer_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.layer_dock.setMinimumWidth(250)
        self.layer_panel = LayerPanel(self.state, self.repository)
        self.layer_panel.settings_modified.connect(self.settings_store.save)
        self.layer_panel.reload_requested.connect(self.reload_map_data)
        self.layer_dock.setWidget(self.layer_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.layer_dock)
        self.layer_dock.setVisible(bool(self.state.settings["layer_panel_visible"]))
        self.layer_dock.visibilityChanged.connect(self._layer_visibility_changed)

    def _replace_layer_panel(self) -> None:
        old_panel = self.layer_panel
        self.layer_panel = LayerPanel(self.state, self.repository)
        self.layer_panel.settings_modified.connect(self.settings_store.save)
        self.layer_panel.reload_requested.connect(self.reload_map_data)
        self.layer_dock.setWidget(self.layer_panel)
        old_panel.deleteLater()

    def _build_status_bar(self) -> None:
        self.clipboard_status = QLabel("Waiting for copied coordinates")
        self.update_time = QLabel("Last update: —")
        self.statusBar().addWidget(self.clipboard_status, 1)
        self.statusBar().addPermanentWidget(self.update_time)

    @Slot(object, object)
    def _on_position_changed(self, current: Position, previous: Position | None) -> None:
        self.clipboard_status.setText("Position updated from copied coordinates")
        self.coordinate_label.setText(f"X {current.x:,.3f}    Y {current.y:,.3f}    Z {current.z:,.3f}")
        local_time = current.timestamp.astimezone()
        self.update_time.setText(f"Last update: {local_time:%H:%M:%S}")
        if previous is None:
            self.previous_label.setText("Previous: —")
            self.heading_label.setText("Heading: —")
        else:
            self.previous_label.setText(
                f"Previous: {previous.x:,.0f}, {previous.y:,.0f}, {previous.z:,.0f}"
            )
            heading = self.state.last_movement_heading
            self.heading_label.setText(
                f"Movement: {cardinal_direction(heading)} {heading:.0f}° · "
                f"{format_distance(self.state.last_movement_distance)}"
                if heading is not None
                else "Movement: no planar change"
            )
        self._update_navigation_labels()
        self._update_nearest_poi()

    def _apply_map_label_font(self) -> None:
        size = min(
            12,
            max(9, int(self.state.settings["poi_label_font_size_full"]) - 1),
        )
        self.nearest_poi_label.setFont(build_map_label_font(self.state.settings, size))

    @Slot()
    def _update_nearest_poi(self) -> None:
        current = self.state.current_position
        if current is None:
            text = "Nearest POI: copy your coordinates to get started"
        else:
            nearest = nearest_named_poi(
                current,
                self.repository.layers,
                self.state.settings["layers"],
            )
            if nearest is None:
                text = "Nearest POI: none in visible layers"
            else:
                direction = (
                    cardinal_direction(nearest.heading)
                    if nearest.heading is not None
                    else "here"
                )
                text = (
                    f"Nearest POI: {nearest.name} · "
                    f"{format_distance(nearest.distance)} · {direction}"
                )
        self.nearest_poi_label.setText(text)
        if self.mini_map is not None:
            self.mini_map.set_nearest_poi_text(text)

    @Slot()
    def _on_settings_changed(self) -> None:
        self._apply_map_label_font()
        self._update_nearest_poi()

    @Slot()
    def _update_navigation_labels(self) -> None:
        current = self.state.current_position
        waypoint = self.state.active_waypoint
        if current is None or waypoint is None:
            self.distance_label.setText("Waypoint: —")
            return
        distance = planar_distance(current, waypoint)
        heading = heading_degrees(current, waypoint)
        self.distance_label.setText(
            f"{waypoint.name}: {format_distance(distance)} · {cardinal_direction(heading)} "
            f"{heading:.0f}°" if heading is not None else f"{waypoint.name}: reached"
        )

    @Slot(float, float)
    def _place_waypoint(self, x: float, y: float) -> None:
        z = self.state.current_position.z if self.state.current_position else 0.0
        existing = self.state.active_waypoint
        name = existing.name if existing else "Active waypoint"
        self.state.set_waypoint(Waypoint(name=name, x=x, y=y, z=z))

    def save_waypoint(self) -> None:
        waypoint = self.state.active_waypoint
        if waypoint is None:
            QMessageBox.information(self, "No waypoint yet", "Right-click the map to place a waypoint first.")
            return
        name, accepted = QInputDialog.getText(self, "Save waypoint", "Marker name:", text=waypoint.name)
        if not accepted or not name.strip():
            return
        saved = Waypoint(name=name.strip(), x=waypoint.x, y=waypoint.y, z=waypoint.z)
        items = list(self.repository.layers.get("custom_markers", []))
        items.append({"name": saved.name, "position": [saved.x, saved.y, saved.z], "description": "Saved waypoint"})
        try:
            self.repository.save_custom_markers(items)
        except OSError as exc:
            QMessageBox.warning(self, "Could not save", f"The local marker file could not be written:\n{exc}")
            return
        self.state.set_waypoint(saved)
        self.map_canvas.render_static_layers()
        if self.mini_map:
            self.mini_map.map_canvas.render_static_layers()
        self._update_nearest_poi()

    def clear_waypoint(self) -> None:
        self.state.set_waypoint(None)

    def clear_breadcrumbs(self) -> None:
        self.state.clear_breadcrumbs()

    def toggle_breadcrumbs(self) -> None:
        enabled = not bool(self.state.settings["breadcrumbs_enabled"])
        self.state.settings["breadcrumbs_enabled"] = enabled
        self.state.settings["layers"]["breadcrumbs"] = enabled
        self.state.layers_changed.emit()
        self.settings_store.save()

    def recenter_player(self) -> None:
        if self.state.current_position is None:
            self.statusBar().showMessage("Waiting for copied coordinates", 2500)
            return
        self.map_canvas.recenter_on_player()

    def _fit_map(self) -> None:
        self.map_canvas.reset_view()

    @Slot(bool)
    def _automatic_tracking_toggled(self, enabled: bool) -> None:
        if not self.windows_features:
            return
        if enabled and CaptureRegion.from_mapping(
            self.state.settings.get("automatic_tracking_region")
        ) is None:
            self.automatic_tracking_action.blockSignals(True)
            self.automatic_tracking_action.setChecked(False)
            self.automatic_tracking_action.blockSignals(False)
            self._begin_automatic_tracking_setup(enable_after_save=True)
            return
        self.state.settings["automatic_tracking_enabled"] = bool(enabled)
        self.settings_store.save()
        self.automatic_tracking_changed.emit(bool(enabled))

    @Slot()
    def open_automatic_tracking_setup(self) -> None:
        """Open setup from the Automatic Tracking toolbar menu."""

        self._begin_automatic_tracking_setup(enable_after_save=False)

    def _begin_automatic_tracking_setup(self, *, enable_after_save: bool) -> None:
        if not self.windows_features:
            self.statusBar().showMessage(
                "Automatic Tracking is available only on Windows", 3500
            )
            return
        self._enable_automatic_after_setup |= enable_after_save
        if self._ocr_setup_dialog is not None:
            self._ocr_setup_dialog.showNormal()
            self._ocr_setup_dialog.raise_()
            self._ocr_setup_dialog.activateWindow()
            return

        # This is intentionally modeless. A nested QDialog.exec() combined with
        # temporarily concealing windows for screen selection can terminate the
        # native modal event loop and, on some Windows/Qt combinations, crash.
        dialog = OcrSetupDialog(self.state.settings, self.project_root)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.finished.connect(
            lambda result, current=dialog: self._automatic_tracking_setup_finished(
                current,
                result,
            )
        )
        self._ocr_setup_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _automatic_tracking_setup_finished(
        self,
        dialog: OcrSetupDialog,
        result: int,
    ) -> None:
        if dialog is not self._ocr_setup_dialog:
            return
        enable_after_save = self._enable_automatic_after_setup
        self._enable_automatic_after_setup = False
        self._ocr_setup_dialog = None
        if result != int(QDialog.DialogCode.Accepted):
            return

        self.state.settings["automatic_tracking_region"] = dialog.region.to_dict()
        should_enable = bool(
            enable_after_save
            or self.state.settings.get("automatic_tracking_enabled", False)
        )
        self.state.settings["automatic_tracking_enabled"] = should_enable
        self.settings_store.save()
        self.automatic_tracking_action.blockSignals(True)
        self.automatic_tracking_action.setChecked(should_enable)
        self.automatic_tracking_action.blockSignals(False)
        self._refresh_automatic_tracking_control()
        self.statusBar().showMessage("Automatic Tracking capture area saved", 3000)
        if should_enable:
            self.automatic_tracking_changed.emit(True)

    def _refresh_automatic_tracking_control(self) -> None:
        configured = CaptureRegion.from_mapping(
            self.state.settings.get("automatic_tracking_region")
        ) is not None
        self.automatic_tracking_setup_action.setText(
            "Change capture area…" if configured else "Set up capture area…"
        )

    def set_automatic_tracking_status(self, enabled: bool, status: str) -> None:
        self.automatic_tracking_action.blockSignals(True)
        self.automatic_tracking_action.setChecked(bool(enabled))
        self.automatic_tracking_action.blockSignals(False)
        self.automatic_tracking_action.setToolTip(status)
        self._refresh_automatic_tracking_control()
        if enabled or status.startswith("Automatic tracking unavailable") or status.startswith("Automatic tracking is not available"):
            self.clipboard_status.setText(status)

    def toggle_layer_panel(self) -> None:
        self.layer_dock.setVisible(not self.layer_dock.isVisible())

    def _layer_visibility_changed(self, visible: bool) -> None:
        self.state.settings["layer_panel_visible"] = visible
        self.settings_store.save()

    def toggle_mini_map(self) -> None:
        if self.mini_map is None:
            return
        if self.mini_map.isVisible():
            self.mini_map.hide()
        else:
            self.mini_map.show()
            self.mini_map.raise_()

    @Slot(bool)
    def _set_mini_map_interaction(self, enabled: bool) -> None:
        if self.mini_map is None:
            self._sync_mini_map_edit_action(False)
            return
        if enabled and not self.mini_map.isVisible():
            self.mini_map.show()
        self.mini_map.set_interaction_enabled(enabled)

    @Slot(bool)
    def _sync_mini_map_edit_action(self, enabled: bool) -> None:
        self.mini_map_edit_action.blockSignals(True)
        self.mini_map_edit_action.setChecked(bool(enabled))
        self.mini_map_edit_action.blockSignals(False)

    def toggle_full_map(self) -> None:
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def toggle_player_centered(self) -> None:
        value = not bool(self.state.settings["player_centered_mode"])
        self.state.settings["player_centered_mode"] = value
        self.settings_store.save()
        if self.mini_map:
            self.mini_map.sync_controls_from_settings()
            if value:
                self.mini_map.map_canvas.recenter_on_player()

    def change_overlay_opacity(self, delta: float) -> None:
        value = min(1.0, max(0.2, float(self.state.settings["overlay_opacity"]) + delta))
        self.state.settings["overlay_opacity"] = round(value, 2)
        self.settings_store.save()
        if self.mini_map:
            self.mini_map.setWindowOpacity(value)

    def reload_map_data(self) -> None:
        self.repository.reload()
        self.map_canvas.render_static_layers()
        if self.mini_map:
            self.mini_map.map_canvas.render_static_layers()
        self._update_nearest_poi()
        self._replace_layer_panel()
        self.statusBar().showMessage("Local map data reloaded", 2500)

    def open_how_to_use(self) -> None:
        dialog = HowToUseDialog(self)
        dialog.exec()

    def open_settings(self) -> None:
        dialog = SettingsWindow(
            self.state.settings,
            self.calibration,
            self.project_root,
            self,
            windows_features=self.windows_features,
        )
        if dialog.exec() != SettingsWindow.DialogCode.Accepted:
            return
        old_data_folder = str(self.state.settings["data_folder"])
        self.state.settings.clear()
        self.state.settings.update(dialog.settings)
        self.settings_store.values = self.state.settings
        self.settings_store.save()
        self.calibration = dialog.calibration
        try:
            save_calibration(self.calibration_path, self.calibration)
        except OSError as exc:
            QMessageBox.warning(self, "Calibration", f"Calibration could not be saved:\n{exc}")
        self.map_canvas.set_calibration(self.calibration)
        self.state.apply_breadcrumb_limit(int(self.state.settings["breadcrumb_max_points"]))
        if self.mini_map:
            self.mini_map.set_calibration(self.calibration)
            self.mini_map.apply_settings()
        if old_data_folder != str(self.state.settings["data_folder"]):
            folder = Path(str(self.state.settings["data_folder"]))
            self.repository.data_folder = folder if folder.is_absolute() else self.project_root / folder
            self.reload_map_data()
        self.state.settings_changed.emit()
        self._replace_layer_panel()
        self.hotkeys_changed.emit()
        self.automatic_tracking_action.blockSignals(True)
        self.automatic_tracking_action.setChecked(
            bool(self.state.settings["automatic_tracking_enabled"])
        )
        self.automatic_tracking_action.blockSignals(False)
        self.automatic_tracking_changed.emit(
            bool(self.state.settings["automatic_tracking_enabled"])
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.tray_available:
            self.hide()
            event.ignore()
        else:
            self.exit_requested.emit()
            event.accept()
