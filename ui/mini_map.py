"""Separate, ordinary desktop mini-map window."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QMouseEvent, QRegion, QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QToolButton,
    QWidget,
)

from core.app_state import AppState
from core.coordinate_transform import MapCalibration
from core.data_loader import LayerRepository
from core.overlay_interaction import apply_windows_overlay_input_style
from ui.map_canvas import MapCanvas
from ui.map_fonts import build_map_label_font


MINI_MAP_FOOTER_HEIGHT = 46
MINI_MAP_FOOTER_INSET = 8


class MiniMapControlStrip(QWidget):
    close_requested = Signal()
    follow_toggled = Signal(bool)
    shape_requested = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._drag_start: QPoint | None = None
        self.setFixedHeight(30)
        self.setStyleSheet(
            """
            MiniMapControlStrip {
                background: rgba(12, 24, 31, 220);
                border: 1px solid rgba(105, 188, 207, 180);
                border-radius: 7px;
            }
            QToolButton {
                color: #dff8fc;
                background: transparent;
                border: 0;
                border-radius: 4px;
                font-weight: 700;
                padding: 2px;
            }
            QToolButton:hover, QToolButton:checked {
                color: #071115;
                background: #6ad8ea;
            }
            """
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        self.follow_button = QToolButton()
        self.follow_button.setText("F")
        self.follow_button.setCheckable(True)
        self.follow_button.setFixedWidth(28)
        self.follow_button.setToolTip("Follow player")
        self.follow_button.toggled.connect(self.follow_toggled)

        self.shape_button = QToolButton()
        self.shape_button.setText("○")
        self.shape_button.setFixedWidth(28)
        self.shape_button.setToolTip("Toggle circle/square")
        self.shape_button.clicked.connect(self.shape_requested)

        drag_label = QLabel("MOVE")
        drag_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drag_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        drag_label.setStyleSheet("color: #82cddb; font-size: 7pt; font-weight: 700; border: 0;")

        close_button = QToolButton()
        close_button.setText("×")
        close_button.setFixedWidth(24)
        close_button.setToolTip("Hide Mini Map")
        close_button.clicked.connect(self.close_requested)

        layout.addWidget(self.follow_button)
        layout.addWidget(self.shape_button)
        layout.addWidget(drag_label, 1)
        layout.addWidget(close_button)

    def update_state(self, follow_player: bool, shape: str) -> None:
        self.follow_button.blockSignals(True)
        self.follow_button.setChecked(follow_player)
        self.follow_button.blockSignals(False)
        self.follow_button.setToolTip(
            "Follow player: on" if follow_player else "Follow player: off"
        )
        self.shape_button.setText("□" if shape == "circle" else "○")
        self.shape_button.setToolTip(
            "Switch to square" if shape == "circle" else "Switch to circle"
        )

    def cancel_drag(self) -> None:
        self._drag_start = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = (
                event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_start)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_start = None
        super().mouseReleaseEvent(event)


class MiniMapResizeHandle(QWidget):
    resize_requested = Signal(int)
    resize_finished = Signal(int)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._drag_origin: QPoint | None = None
        self._start_side = 0
        self._current_side = 0
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setToolTip("Drag to resize Mini Map")
        self.setStyleSheet(
            """
            background: rgba(12, 24, 31, 220);
            border: 1px solid rgba(105, 188, 207, 190);
            border-radius: 8px;
            """
        )
        label = QLabel("↘", self)
        label.setGeometry(0, 0, 28, 28)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        label.setStyleSheet("color: #9de7f2; font-weight: 700; border: 0; background: transparent;")

    def cancel_drag(self) -> None:
        self._drag_origin = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint()
            self._start_side = self.window().width()
            self._current_side = self._start_side
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_origin
            dominant_delta = delta.x() if abs(delta.x()) >= abs(delta.y()) else delta.y()
            self._current_side = min(1200, max(180, self._start_side + dominant_delta))
            self.resize_requested.emit(self._current_side)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_origin is not None:
            self._drag_origin = None
            self.resize_finished.emit(self._current_side)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class MiniMapWindow(QWidget):
    waypoint_requested = Signal(float, float)
    waypoint_clear_requested = Signal()
    settings_modified = Signal()
    interaction_changed = Signal(bool)

    def __init__(
        self,
        map_path: Path,
        calibration: MapCalibration,
        repository: LayerRepository,
        state: AppState,
    ) -> None:
        super().__init__()
        self.state = state
        self._enforcing_square = False
        self._interaction_enabled = False
        self._position_initialized = False
        self._nearest_poi_text = "Nearest POI: waiting for copied coordinates"
        self.setWindowTitle("The Isle Companion — Mini Map")
        self.setMinimumSize(180, 180 + MINI_MAP_FOOTER_HEIGHT)
        self.setMaximumSize(1200, 1200 + MINI_MAP_FOOTER_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("MiniMapWindow { background: transparent; }")

        self.map_canvas = MapCanvas(
            map_path,
            calibration,
            repository,
            state,
            compact=True,
        )
        self.map_canvas.setParent(self)
        self.map_canvas.waypoint_requested.connect(self.waypoint_requested)
        self.map_canvas.waypoint_clear_requested.connect(self.waypoint_clear_requested)

        self.nearest_poi_label = QLabel(self._nearest_poi_text, self)
        self.nearest_poi_label.setObjectName("miniNearestPoiLabel")
        self.nearest_poi_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nearest_poi_label.setWordWrap(True)
        self.nearest_poi_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self.nearest_poi_label.setStyleSheet(
            """
            QLabel#miniNearestPoiLabel {
                color: #f0fbfd;
                background: rgba(12, 24, 31, 232);
                border: 1px solid rgba(80, 151, 167, 210);
                border-radius: 8px;
                padding: 2px 6px;
            }
            """
        )
        state.settings_changed.connect(self._apply_nearest_label_font)

        self.control_strip = MiniMapControlStrip(self)
        self.control_strip.close_requested.connect(self.hide)
        self.control_strip.follow_toggled.connect(self._set_follow_player)
        self.control_strip.shape_requested.connect(self._toggle_shape)

        self.resize_handle = MiniMapResizeHandle(self)
        self.resize_handle.resize_requested.connect(self._resize_from_handle)
        self.resize_handle.resize_finished.connect(self._finish_resize)

        self.apply_settings()
        self.set_interaction_enabled(False)

    @property
    def interaction_enabled(self) -> bool:
        return self._interaction_enabled

    def _window_flags(self, *, interactable: bool | None = None) -> Qt.WindowType:
        if interactable is None:
            interactable = self._interaction_enabled
        settings = self.state.settings
        flags = Qt.WindowType.Window
        if settings["overlay_borderless"]:
            flags |= Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
        if settings["always_on_top"]:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        if not interactable:
            flags |= Qt.WindowType.WindowTransparentForInput
        return flags

    def apply_settings(self) -> None:
        settings = self.state.settings
        was_visible = self.isVisible()
        self.setWindowFlags(self._window_flags())
        size = int(settings["overlay_size"])
        self._set_map_side(size)
        self.setWindowOpacity(float(settings["overlay_opacity"]))
        self._apply_nearest_label_font()
        self.control_strip.update_state(
            bool(settings["player_centered_mode"]), str(settings["overlay_shape"])
        )
        self._apply_mask()
        self._position_overlay_controls()
        if was_visible:
            self.show()
        QTimer.singleShot(0, self._reapply_input_style)

    def _apply_nearest_label_font(self) -> None:
        settings = self.state.settings
        footer_size = min(
            10,
            max(8, int(settings["poi_label_font_size_mini"])),
        )
        self.nearest_poi_label.setFont(
            build_map_label_font(settings, footer_size)
        )

    def set_interaction_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        changed = enabled != self._interaction_enabled
        if changed:
            was_visible = self.isVisible()
            self._interaction_enabled = enabled
            # Clear the Qt-level transparent attribute before rebuilding flags;
            # otherwise Qt re-adds WindowTransparentForInput during setWindowFlags.
            self.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                not self._interaction_enabled,
            )
            self.setWindowFlags(self._window_flags(interactable=enabled))
            if was_visible:
                self.show()
        else:
            self._interaction_enabled = enabled
            self.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                not self._interaction_enabled,
            )
        self.control_strip.setVisible(self._interaction_enabled)
        self.resize_handle.setVisible(self._interaction_enabled)
        if not self._interaction_enabled:
            self.control_strip.cancel_drag()
            self.resize_handle.cancel_drag()
            self.map_canvas.cancel_mouse_interaction()
        self._position_overlay_controls()
        self._reapply_input_style()
        if changed:
            self.interaction_changed.emit(self._interaction_enabled)

    def _reapply_input_style(self) -> None:
        if os.name != "nt" or QGuiApplication.platformName().lower() != "windows":
            return
        apply_windows_overlay_input_style(int(self.winId()), self._interaction_enabled)

    def _set_follow_player(self, enabled: bool) -> None:
        self.state.settings["player_centered_mode"] = bool(enabled)
        if enabled:
            self.map_canvas.recenter_on_player()
        self.settings_modified.emit()

    def sync_controls_from_settings(self) -> None:
        self.control_strip.update_state(
            bool(self.state.settings["player_centered_mode"]),
            str(self.state.settings["overlay_shape"]),
        )

    def _toggle_shape(self) -> None:
        current = str(self.state.settings["overlay_shape"])
        self.state.settings["overlay_shape"] = "circle" if current == "square" else "square"
        self.control_strip.update_state(
            bool(self.state.settings["player_centered_mode"]),
            str(self.state.settings["overlay_shape"]),
        )
        # Recreate the native frame after a shape change.  Windows otherwise
        # can retain the old square DWM outline when an ellipse mask is applied
        # for a second time.
        was_visible = self.isVisible()
        self.clearMask()
        self.setWindowFlags(self._window_flags())
        self._apply_mask()
        self._position_overlay_controls()
        if was_visible:
            self.show()
            self.raise_()
        self.update()
        QTimer.singleShot(0, self._reapply_input_style)
        self.settings_modified.emit()

    def _resize_from_handle(self, side: int) -> None:
        self._set_map_side(side)

    def _finish_resize(self, side: int) -> None:
        side = min(1200, max(180, int(side)))
        self.state.settings["overlay_size"] = side
        self._set_map_side(side)
        self.settings_modified.emit()

    def _set_map_side(self, side: int) -> None:
        side = min(1200, max(180, int(side)))
        self._enforcing_square = True
        self.resize(side, side + MINI_MAP_FOOTER_HEIGHT)
        self._enforcing_square = False
        self._layout_overlay(side)
        self._apply_mask()
        self._position_overlay_controls()

    def _layout_overlay(self, side: int) -> None:
        self.map_canvas.setGeometry(0, 0, side, side)
        self.nearest_poi_label.setGeometry(
            MINI_MAP_FOOTER_INSET,
            side + 4,
            max(1, side - MINI_MAP_FOOTER_INSET * 2),
            MINI_MAP_FOOTER_HEIGHT - 8,
        )
        self.nearest_poi_label.raise_()

    def set_nearest_poi_text(self, text: str) -> None:
        """Update the persistent Mini Map footer without affecting input state."""

        self._nearest_poi_text = str(text)
        parts = self._nearest_poi_text.split(" · ")
        display_text = (
            f"{parts[0]}\n{' · '.join(parts[1:])}"
            if len(parts) >= 3
            else self._nearest_poi_text
        )
        self.nearest_poi_label.setText(display_text)
        self.nearest_poi_label.setToolTip(self._nearest_poi_text)

    def _apply_mask(self) -> None:
        self.clearMask()
        if self.state.settings["overlay_shape"] == "circle":
            side = self.map_canvas.width()
            map_region = QRegion(
                QRect(0, 0, side, side),
                QRegion.RegionType.Ellipse,
            )
            footer_region = QRegion(self.nearest_poi_label.geometry())
            self.setMask(map_region.united(footer_region))
        self.update()
        self.map_canvas.viewport().update()

    def _position_overlay_controls(self) -> None:
        side = self.map_canvas.width()
        if self.state.settings["overlay_shape"] == "circle":
            horizontal_inset = max(24, int(side * 0.15))
            top = max(14, int(side * 0.08))
            handle_x = int(side * 0.78 - self.resize_handle.width() / 2)
            handle_y = int(side * 0.78 - self.resize_handle.height() / 2)
        else:
            horizontal_inset = 8
            top = 8
            handle_x = side - self.resize_handle.width() - 10
            handle_y = side - self.resize_handle.height() - 10
        strip_width = max(120, side - horizontal_inset * 2)
        self.control_strip.setGeometry(horizontal_inset, top, strip_width, 30)
        self.resize_handle.move(
            min(side - self.resize_handle.width(), handle_x),
            min(side - self.resize_handle.height(), handle_y),
        )
        self.control_strip.raise_()
        self.resize_handle.raise_()
        self.nearest_poi_label.raise_()

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)  # type: ignore[arg-type]
        if not hasattr(self, "map_canvas"):
            return
        if not self._enforcing_square:
            new_size = event.size()  # type: ignore[attr-defined]
            old_size = event.oldSize()  # type: ignore[attr-defined]
            width_delta = abs(new_size.width() - old_size.width())
            height_delta = abs(new_size.height() - old_size.height())
            side = (
                new_size.width()
                if width_delta >= height_delta
                else new_size.height() - MINI_MAP_FOOTER_HEIGHT
            )
            side = min(1200, max(180, side))
            if (
                new_size.width() != side
                or new_size.height() != side + MINI_MAP_FOOTER_HEIGHT
            ):
                self._set_map_side(side)
                return
        side = self.width()
        self._layout_overlay(side)
        self._apply_mask()
        self._position_overlay_controls()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._position_initialized:
            screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
            if screen is not None:
                available = screen.availableGeometry()
                self.move(available.right() - self.width() - 16, available.top() + 16)
            self._position_initialized = True
        QTimer.singleShot(0, self._reapply_input_style)

    def set_calibration(self, calibration: MapCalibration) -> None:
        self.map_canvas.set_calibration(calibration)
