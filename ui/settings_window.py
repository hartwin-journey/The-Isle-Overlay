"""Settings editor for local behavior, hotkeys, and map calibration."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.coordinate_transform import MapCalibration
from core.hotkeys import parse_hold_binding
from core.map_fonts import MAP_LABEL_FONT_PRESETS


_MODIFIER_NAMES = (
    (Qt.KeyboardModifier.ControlModifier, "Ctrl"),
    (Qt.KeyboardModifier.ShiftModifier, "Shift"),
    (Qt.KeyboardModifier.AltModifier, "Alt"),
    (Qt.KeyboardModifier.MetaModifier, "Win"),
)

_PURE_MODIFIER_KEYS = {
    Qt.Key.Key_Control,
    Qt.Key.Key_Shift,
    Qt.Key.Key_Alt,
    Qt.Key.Key_Meta,
}

_SPECIAL_KEY_NAMES = {
    Qt.Key.Key_PageUp: "PageUp",
    Qt.Key.Key_PageDown: "PageDown",
    Qt.Key.Key_Home: "Home",
    Qt.Key.Key_End: "End",
    Qt.Key.Key_Insert: "Insert",
    Qt.Key.Key_Delete: "Delete",
    Qt.Key.Key_Space: "Space",
}

_MOUSE_BUTTON_NAMES = {
    Qt.MouseButton.BackButton: "M4",
    Qt.MouseButton.ForwardButton: "M5",
}

_ZONE_OPACITY_BASELINES = {
    "migrations": 0.42,
    "patrol_zones": 0.33,
    "sanctuaries": 0.60,
}

_MARKER_OPACITY_KEYS = (
    "updrafts",
    "locations",
    "food",
    "ai",
    "salt_licks",
    "spawns",
    "custom_markers",
)

_SHORTCUT_LABELS = {
    "toggle_full_map": "Show/hide Full Map",
    "toggle_mini_map": "Show/hide Mini Map",
    "toggle_layer_panel": "Show/hide layer panel",
    "toggle_breadcrumbs": "Toggle breadcrumbs",
    "clear_waypoint": "Clear active waypoint",
    "recenter_player": "Recenter on player",
    "toggle_player_centered": "Toggle player-centered Mini Map",
    "increase_opacity": "Increase overlay opacity",
    "decrease_opacity": "Decrease overlay opacity",
}


class HotkeyCaptureButton(QPushButton):
    """Button that captures the next supported keyboard or mouse shortcut."""

    def __init__(self, value: str, parent: QWidget | None = None) -> None:
        super().__init__(value, parent)
        self._value = value
        self._capturing = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip("Click, then press a keyboard shortcut or M4/M5 mouse button")
        self.clicked.connect(self._begin_capture)

    def _begin_capture(self) -> None:
        self._capturing = True
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.setText("Press shortcut…  (Esc cancels)")

    def _finish_capture(self, value: str) -> None:
        self._capturing = False
        self._value = value
        self.setText(value)

    def _cancel_capture(self) -> None:
        self._capturing = False
        self.setText(self._value)

    @staticmethod
    def _modifier_prefix(modifiers: Qt.KeyboardModifier) -> list[str]:
        return [name for modifier, name in _MODIFIER_NAMES if modifiers & modifier]

    @staticmethod
    def _key_name(event: QKeyEvent) -> str | None:
        key = event.key()
        if key in _PURE_MODIFIER_KEYS:
            return None
        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            return chr(ord("A") + key - Qt.Key.Key_A)
        if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            return chr(ord("0") + key - Qt.Key.Key_0)
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
            return f"F{key - Qt.Key.Key_F1 + 1}"
        return _SPECIAL_KEY_NAMES.get(Qt.Key(key))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._capturing:
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key.Key_Escape:
            self._cancel_capture()
            event.accept()
            return
        key_name = self._key_name(event)
        if key_name is None:
            event.accept()
            return
        self._finish_capture("+".join(self._modifier_prefix(event.modifiers()) + [key_name]))
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._capturing:
            super().mousePressEvent(event)
            return
        button_name = _MOUSE_BUTTON_NAMES.get(event.button())
        if button_name is None:
            event.accept()
            return
        self._finish_capture("+".join(self._modifier_prefix(event.modifiers()) + [button_name]))
        event.accept()


class SettingsWindow(QDialog):
    def __init__(
        self,
        settings: dict[str, Any],
        calibration: MapCalibration,
        project_root: Path,
        parent: QWidget | None = None,
        *,
        windows_features: bool | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("The Isle Companion — Settings")
        self.setMinimumSize(700, 610)
        self._settings = copy.deepcopy(settings)
        self._calibration = calibration
        self.windows_features = (
            os.name == "nt" if windows_features is None else bool(windows_features)
        )
        self._checks: dict[str, QCheckBox] = {}
        self._layer_opacity_sliders: dict[str, QSlider] = {}
        self._hotkeys: dict[str, HotkeyCaptureButton] = {}
        self._calibration_fields: dict[str, QDoubleSpinBox] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(self._build_general_tab(), "Mini Map")
        tabs.addTab(self._build_map_tab(), "Map & Tracking")
        if self.windows_features:
            tabs.addTab(self._build_hotkeys_tab(), "Shortcuts")
        tabs.addTab(self._build_calibration_tab(), "Advanced")
        layout.addWidget(tabs)

        note_text = (
            "OFFLINE  •  CLIPBOARD OR SELECTED SCREEN PIXELS  •  NO TELEMETRY"
            if self.windows_features
            else "OFFLINE  •  CLIPBOARD ONLY  •  NO TELEMETRY"
        )
        note = QLabel(note_text)
        note.setObjectName("privacyNote")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_values)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _check(self, key: str, label: str) -> QCheckBox:
        control = QCheckBox(label)
        control.setChecked(bool(self._settings[key]))
        self._checks[key] = control
        return control

    def _build_general_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        introduction = QLabel(
            (
                "During play, the Mini Map starts in click-through mode so it stays out "
                "of the way. Press M4 once when you want to resize, zoom, pan, or toggle "
                "follow mode, then press it again to lock the overlay back down. You can "
                "change that binding in Settings > Shortcuts."
                if self.windows_features
                else "Use Edit Mini Map in the Full Map toolbar when you want to move, "
                "zoom, or resize the overlay; turn it off again before returning to the game."
            )
        )
        introduction.setWordWrap(True)
        introduction.setObjectName("sectionNote")
        layout.addWidget(introduction)

        behavior = QGroupBox("Behavior")
        behavior_layout = QVBoxLayout(behavior)
        behavior_layout.addWidget(
            self._check("launch_mini_map_on_startup", "Open Mini Map when the companion starts")
        )
        behavior_layout.addWidget(self._check("always_on_top", "Keep Mini Map above other windows"))
        behavior_layout.addWidget(
            self._check("player_centered_mode", "Follow the player after each copied location")
        )
        layout.addWidget(behavior)

        overlay = QGroupBox("Appearance")
        form = QFormLayout(overlay)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)

        self.overlay_shape = QComboBox()
        self.overlay_shape.addItem("Square", "square")
        self.overlay_shape.addItem("Circle", "circle")
        shape_index = self.overlay_shape.findData(str(self._settings["overlay_shape"]))
        self.overlay_shape.setCurrentIndex(max(0, shape_index))
        form.addRow("Shape", self.overlay_shape)

        self.overlay_size = QSpinBox()
        self.overlay_size.setRange(180, 1200)
        self.overlay_size.setSingleStep(20)
        self.overlay_size.setSuffix(" px")
        self.overlay_size.setValue(int(self._settings["overlay_size"]))
        form.addRow("Size", self.overlay_size)

        self.opacity = self._opacity_control(
            round(float(self._settings["overlay_opacity"]) * 100),
            "overlay",
        )
        form.addRow("Window opacity", self.opacity)
        layout.addWidget(overlay)
        layout.addStretch()
        return tab

    @staticmethod
    def _average_zone_intensity(layer_opacity: dict[str, Any]) -> int:
        """Collapse the three zone layers into one friendly slider value."""
        total = sum(
            float(layer_opacity.get(key, baseline)) / baseline
            for key, baseline in _ZONE_OPACITY_BASELINES.items()
        )
        return round(total * (100 / len(_ZONE_OPACITY_BASELINES)))

    @staticmethod
    def _average_marker_opacity(layer_opacity: dict[str, Any]) -> int:
        """Treat individual marker layers as one visual weight control."""
        total = sum(float(layer_opacity.get(key, 1.0)) for key in _MARKER_OPACITY_KEYS)
        return round(total / len(_MARKER_OPACITY_KEYS) * 100)

    def _opacity_control(self, value: int, key: str) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(10 if key != "overlay" else 20, 100)
        slider.setSingleStep(5)
        slider.setPageStep(10)
        slider.setValue(value)
        value_label = QLabel(f"{value}%")
        value_label.setObjectName("sliderValue")
        value_label.setMinimumWidth(44)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        slider.valueChanged.connect(lambda current: value_label.setText(f"{current}%"))
        row_layout.addWidget(slider, 1)
        row_layout.addWidget(value_label)
        if key == "overlay":
            self._overlay_opacity_slider = slider
        else:
            self._layer_opacity_sliders[key] = slider
        return row

    def _build_map_tab(self) -> QWidget:
        tab = QScrollArea()
        tab.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        explanation = QLabel(
            "Layer visibility is managed from the Layers panel on the Full Map. "
            "These controls only tune visual clarity."
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("sectionNote")
        layout.addWidget(explanation)

        opacity_group = QGroupBox("Visual balance")
        opacity_form = QFormLayout(opacity_group)
        opacity_form.setHorizontalSpacing(18)
        opacity_form.setVerticalSpacing(12)
        layer_opacity = self._settings["layer_opacity"]
        zone_value = self._average_zone_intensity(layer_opacity)
        marker_value = self._average_marker_opacity(layer_opacity)
        opacity_form.addRow("Zone intensity", self._opacity_control(zone_value, "zones"))
        opacity_form.addRow(
            "Water",
            self._opacity_control(round(float(layer_opacity.get("water", 1.0)) * 100), "water"),
        )
        opacity_form.addRow("POI markers", self._opacity_control(marker_value, "markers"))
        layout.addWidget(opacity_group)

        label_group = QGroupBox("POI names")
        label_form = QFormLayout(label_group)
        self.full_label_size = QSpinBox()
        self.full_label_size.setRange(7, 18)
        self.full_label_size.setSuffix(" pt")
        self.full_label_size.setValue(int(self._settings["poi_label_font_size_full"]))
        label_form.addRow("Label size", self.full_label_size)

        self.map_label_font = QComboBox()
        for preset_id, preset in MAP_LABEL_FONT_PRESETS.items():
            self.map_label_font.addItem(preset.label, preset_id)
        font_index = self.map_label_font.findData(
            str(self._settings.get("map_label_font_preset", "segoe_semibold"))
        )
        self.map_label_font.setCurrentIndex(max(0, font_index))
        label_form.addRow("Map label typeface", self.map_label_font)

        label_form.addRow(
            self._check("mini_map_show_poi_labels", "Show POI names on the Mini Map")
        )
        label_note = QLabel("Names hide automatically at overview zoom to keep the map readable.")
        label_note.setWordWrap(True)
        label_note.setObjectName("fieldHint")
        label_form.addRow("", label_note)
        layout.addWidget(label_group)

        tracking_group = QGroupBox("Breadcrumb trail")
        tracking_form = QFormLayout(tracking_group)
        tracking_form.addRow(
            self._check("breadcrumbs_enabled", "Show a trail for valid copied positions")
        )
        self.breadcrumb_limit = QSpinBox()
        self.breadcrumb_limit.setRange(25, 2_000)
        self.breadcrumb_limit.setSingleStep(25)
        self.breadcrumb_limit.setValue(int(self._settings["breadcrumb_max_points"]))
        tracking_form.addRow("History length", self.breadcrumb_limit)
        tracking_note = QLabel("The trail stays local and is cleared when the application exits.")
        tracking_note.setWordWrap(True)
        tracking_note.setObjectName("fieldHint")
        tracking_form.addRow("", tracking_note)
        layout.addWidget(tracking_group)
        layout.addStretch()
        tab.setWidget(body)
        return tab

    def _build_hotkeys_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        label = QLabel(
            "Shortcuts are listened for at normal Windows user level. The companion never "
            "suppresses, injects, or forwards them to the game."
        )
        label.setWordWrap(True)
        label.setObjectName("sectionNote")
        layout.addWidget(label)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QFormLayout(body)
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(9)

        self.interaction_hold_key = HotkeyCaptureButton(
            str(self._settings["overlay_interaction_hold_key"])
        )
        form.addRow("Toggle Mini Map editing", self.interaction_hold_key)

        for key, name in _SHORTCUT_LABELS.items():
            field = HotkeyCaptureButton(str(self._settings["hotkeys"].get(key, "")))
            self._hotkeys[key] = field
            form.addRow(name, field)
        scroll.setWidget(body)
        layout.addWidget(scroll)
        return tab

    def _calibration_spin(self, value: float) -> QDoubleSpinBox:
        control = QDoubleSpinBox()
        control.setRange(-1_000_000_000.0, 1_000_000_000.0)
        control.setDecimals(3)
        control.setValue(value)
        return control

    def _build_calibration_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        explanation = QLabel(
            "Map calibration normally requires no adjustment. Change these values only when "
            "aligning a replacement Gateway image against known coordinates."
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("sectionNote")
        layout.addWidget(explanation)
        group = QGroupBox("Map calibration")
        form = QFormLayout(group)
        values = {
            "world_min_x": self._calibration.world_min_x,
            "world_max_x": self._calibration.world_max_x,
            "world_min_y": self._calibration.world_min_y,
            "world_max_y": self._calibration.world_max_y,
            "pixel_min_x": self._calibration.pixel_min_x,
            "pixel_max_x": self._calibration.pixel_max_x,
            "pixel_min_y": self._calibration.pixel_min_y,
            "pixel_max_y": self._calibration.pixel_max_y,
        }
        labels = {
            "world_min_x": "World minimum X",
            "world_max_x": "World maximum X",
            "world_min_y": "World minimum Y",
            "world_max_y": "World maximum Y",
            "pixel_min_x": "Pixel minimum X",
            "pixel_max_x": "Pixel maximum X",
            "pixel_min_y": "Pixel minimum Y",
            "pixel_max_y": "Pixel maximum Y",
        }
        for key, value in values.items():
            field = self._calibration_spin(value)
            self._calibration_fields[key] = field
            form.addRow(labels[key], field)
        self.invert_y = QCheckBox("Invert map Y axis")
        self.invert_y.setChecked(self._calibration.invert_y)
        form.addRow(self.invert_y)
        self.invert_x = QCheckBox("Invert map X axis")
        self.invert_x.setChecked(self._calibration.invert_x)
        form.addRow(self.invert_x)
        self.swap_axes = QCheckBox("Swap world X/Y axes")
        self.swap_axes.setChecked(self._calibration.swap_axes)
        form.addRow(self.swap_axes)
        layout.addWidget(group)
        layout.addStretch()
        return tab

    def _accept_values(self) -> None:
        for key, checkbox in self._checks.items():
            self._settings[key] = checkbox.isChecked()
        self._settings["overlay_opacity"] = self._overlay_opacity_slider.value() / 100.0
        self._settings["overlay_size"] = self.overlay_size.value()
        self._settings["overlay_shape"] = str(self.overlay_shape.currentData())
        self._settings["breadcrumb_max_points"] = self.breadcrumb_limit.value()
        self._settings["poi_label_font_size_full"] = self.full_label_size.value()
        self._settings["poi_label_font_size_mini"] = max(
            6,
            min(18, self.full_label_size.value() - 2),
        )
        self._settings["map_label_font_preset"] = str(
            self.map_label_font.currentData()
        )
        self._settings["layers"]["breadcrumbs"] = bool(
            self._settings["breadcrumbs_enabled"]
        )
        if self.windows_features:
            hold_binding = self.interaction_hold_key.text().strip()
            try:
                parse_hold_binding(hold_binding)
            except ValueError as exc:
                QMessageBox.warning(self, "Invalid interaction binding", str(exc))
                self.interaction_hold_key.setFocus(Qt.FocusReason.OtherFocusReason)
                return
            self._settings["overlay_interaction_hold_key"] = hold_binding
            for key, field in self._hotkeys.items():
                self._settings["hotkeys"][key] = field.text().strip()
        zone_intensity = self._layer_opacity_sliders["zones"].value() / 100.0
        for key, baseline in _ZONE_OPACITY_BASELINES.items():
            self._settings["layer_opacity"][key] = round(baseline * zone_intensity, 3)
        self._settings["layer_opacity"]["water"] = (
            self._layer_opacity_sliders["water"].value() / 100.0
        )
        marker_opacity = self._layer_opacity_sliders["markers"].value() / 100.0
        for key in _MARKER_OPACITY_KEYS:
            self._settings["layer_opacity"][key] = marker_opacity

        values = {key: field.value() for key, field in self._calibration_fields.items()}
        candidate = MapCalibration(
            **values,
            invert_y=self.invert_y.isChecked(),
            invert_x=self.invert_x.isChecked(),
            swap_axes=self.swap_axes.isChecked(),
        )
        try:
            candidate.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid calibration", str(exc))
            self._calibration_fields["world_min_x"].setFocus(Qt.FocusReason.OtherFocusReason)
            return
        self._calibration = candidate
        self.accept()

    @property
    def settings(self) -> dict[str, Any]:
        return self._settings

    @property
    def calibration(self) -> MapCalibration:
        return self._calibration
