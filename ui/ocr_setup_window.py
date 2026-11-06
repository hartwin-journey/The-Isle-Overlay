"""User-guided setup for the pixel-only automatic tracking region."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import (
    QObject,
    QPoint,
    QRect,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QColor,
    QCloseEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QScreen,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.automatic_tracking import parse_coordinates_from_ocr
from core.coordinate_parser import CoordinateParseError
from core.environment import detect as detect_environment
from core.local_ocr import (
    OcrEngine,
    OcrRecognitionError,
    OcrUnavailableError,
    create_ocr_engine,
)
from core.screen_capture import (
    CaptureRegion,
    ScreenCaptureError,
    ScreenCaptureService,
    is_wayland_session,
)
from core.wayland_layer_overlay import WaylandLayerOverlay
from core.x11_overlay import x11_overlay_active


class ScreenRegionSelector(QWidget):
    """Temporary desktop overlay used only for region selection.

    Without a backdrop it is a transparent window spanning every monitor
    (Windows, macOS, X11). Wayland does not let applications place windows at
    global positions, so there one selector per monitor shows a frozen
    screenshot of that monitor. It is a layer-shell overlay where supported,
    an X11 override-redirect window on GNOME, and a fullscreen window
    otherwise, so it appears above a fullscreen game.
    """

    region_selected = Signal(object)
    cancelled = Signal()

    def __init__(
        self,
        screen: QScreen | None = None,
        backdrop: QPixmap | None = None,
    ) -> None:
        super().__init__()
        self._origin: QPoint | None = None
        self._selection = QRect()
        self._screen = screen
        self._backdrop = backdrop
        if screen is not None:
            self._virtual_geometry = QRect(screen.geometry())
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
            )
        else:
            self._virtual_geometry = ScreenCaptureService.virtual_geometry()
            self.setWindowFlags(
                Qt.WindowType.Tool
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setGeometry(self._virtual_geometry)
        # On layer-shell compositors the picker is an overlay that appears
        # above the game on whichever workspace is showing. A normal window
        # could open behind a fullscreen game instead.
        self.layer_overlay = (
            WaylandLayerOverlay.create(
                self, namespace="isle-companion-area-picker", keyboard=True
            )
            if screen is not None
            else None
        )
        if self.layer_overlay is not None:
            self.layer_overlay.set_interactive(True)
        # GNOME (via XWayland): bypass the window manager so the picker
        # cannot open behind a fullscreen game.
        self._x11_overlay = (
            screen is not None and self.layer_overlay is None and x11_overlay_active()
        )
        if self._x11_overlay:
            self.setWindowFlags(
                Qt.WindowType.Window
                | Qt.WindowType.X11BypassWindowManagerHint
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
            )

    def present(self) -> None:
        if self._screen is None:
            self.show()
            return
        if self.layer_overlay is not None or self._x11_overlay:
            self.setGeometry(self._virtual_geometry)
            self.show()
            if self._x11_overlay:
                self.raise_()
                # Unmanaged windows never get focus; grab Esc explicitly.
                self.grabKeyboard()
            return
        self.setScreen(self._screen)
        self.showFullScreen()

    def dispose(self) -> None:
        if self._x11_overlay:
            self.releaseKeyboard()
        self.hide()
        if self.layer_overlay is not None:
            self.layer_overlay.close()
        self.deleteLater()

    def _local_to_global(self, selection: QRect) -> QRect:
        if self._screen is None or self.width() <= 0 or self.height() <= 0:
            return selection.translated(self._virtual_geometry.topLeft())
        # Full screen widgets match the monitor's logical size; scale anyway
        # in case the compositor resized the surface.
        scale_x = self._virtual_geometry.width() / self.width()
        scale_y = self._virtual_geometry.height() / self.height()
        return QRect(
            self._virtual_geometry.x() + round(selection.x() * scale_x),
            self._virtual_geometry.y() + round(selection.y() * scale_y),
            round(selection.width() * scale_x),
            round(selection.height() * scale_y),
        )

    def showEvent(self, event: object) -> None:
        super().showEvent(event)  # type: ignore[arg-type]
        self.activateWindow()
        self.raise_()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        if self._backdrop is not None:
            painter.drawPixmap(self.rect(), self._backdrop)
            painter.fillRect(self.rect(), QColor(3, 9, 13, 150))
            if not self._selection.isNull():
                # Show the frozen pixels undimmed inside the selection.
                sx = self._backdrop.width() / max(1, self.width())
                sy = self._backdrop.height() / max(1, self.height())
                selection = self._selection
                source = QRect(
                    round(selection.x() * sx),
                    round(selection.y() * sy),
                    round(selection.width() * sx),
                    round(selection.height() * sy),
                )
                painter.drawPixmap(selection, self._backdrop, source)
        else:
            painter.fillRect(self.rect(), QColor(3, 9, 13, 150))
            if not self._selection.isNull():
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
                painter.fillRect(self._selection, Qt.GlobalColor.transparent)
                painter.setCompositionMode(
                    QPainter.CompositionMode.CompositionMode_SourceOver
                )
        if not self._selection.isNull():
            pen = QPen(QColor("#45d7ef"), 2)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawRect(self._selection.adjusted(0, 0, -1, -1))
        painter.setPen(QColor("#f2fbfd"))
        font = painter.font()
        font.setPointSize(13)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            self.rect().adjusted(24, 20, -24, -20),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
            "Drag around the coordinate text  •  Esc or right-click to cancel",
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            # Works even where an overlay cannot receive Esc.
            self.hide()
            self.cancelled.emit()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._selection = QRect(self._origin, self._origin)
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._selection = QRect(
                self._origin,
                event.position().toPoint(),
            ).normalized()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._origin is not None:
            selection = QRect(self._selection)
            self._origin = None
            if selection.width() >= 32 and selection.height() >= 16:
                mapped = self._local_to_global(selection)
                global_region = CaptureRegion(
                    x=mapped.x(),
                    y=mapped.y(),
                    width=mapped.width(),
                    height=mapped.height(),
                )
                self.hide()
                self.region_selected.emit(global_region)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.cancelled.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class _PreviewSignals(QObject):
    finished = Signal(object, object)


class _PreviewWorker(QRunnable):
    """Recognize one setup preview without blocking the Qt UI thread."""

    def __init__(self, engine: OcrEngine, png_bytes: bytes) -> None:
        super().__init__()
        self.engine = engine
        self.png_bytes = png_bytes
        self.signals = _PreviewSignals()

    @Slot()
    def run(self) -> None:
        try:
            text = self.engine.recognize_png(self.png_bytes)
        except (OcrUnavailableError, OcrRecognitionError) as exc:
            self.signals.finished.emit(None, exc)
            return
        self.signals.finished.emit(text, None)


class OcrSetupDialog(QDialog):
    """Select, adjust, capture, and preview the configured OCR area."""

    def __init__(
        self,
        settings: dict[str, object],
        project_root: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Automatic Tracking Setup")
        self.setMinimumSize(720, 590)
        self.capture_service = ScreenCaptureService()
        self.ocr_engine = create_ocr_engine(project_root)
        self._thread_pool = QThreadPool.globalInstance()
        self._windows_to_restore: list[QWidget] = []
        self._selectors: list[ScreenRegionSelector] = []
        self._wayland = is_wayland_session()
        self._preview_busy = False
        self._saved_window_opacity = 1.0
        self._region = CaptureRegion.from_mapping(
            settings.get("automatic_tracking_region")
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        explanation = QLabel(
            "Open The Isle's Tab menu, then select only the visible coordinate line. "
            "The companion captures these screen pixels normally and processes them "
            "locally; it never accesses or sends input to the game. The default Mini Map "
            "editing toggle is M4 (mouse button 4); use it to zoom, pan, and toggle "
            "player follow, or change it later in Settings."
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("sectionNote")
        layout.addWidget(explanation)

        region_group = QGroupBox("Capture area")
        region_layout = QVBoxLayout(region_group)
        fields = QHBoxLayout()
        self.x_field = self._coordinate_field(-100_000, 100_000)
        self.y_field = self._coordinate_field(-100_000, 100_000)
        self.width_field = self._coordinate_field(32, 4096)
        self.height_field = self._coordinate_field(16, 2160)
        for label, field in (
            ("X", self.x_field),
            ("Y", self.y_field),
            ("Width", self.width_field),
            ("Height", self.height_field),
        ):
            column = QVBoxLayout()
            column.addWidget(QLabel(label))
            column.addWidget(field)
            fields.addLayout(column)
        region_layout.addLayout(fields)

        buttons = QHBoxLayout()
        self.select_button = QPushButton("Select area on screen")
        self.select_button.clicked.connect(self._select_area)
        self.preview_button = QPushButton("Capture and preview")
        self.preview_button.clicked.connect(self._preview_current_area)
        # A countdown lets the player switch to the game first, e.g. when the
        # game is fullscreen or on another workspace/virtual desktop.
        self.delay_field = QSpinBox()
        self.delay_field.setRange(0, 15)
        self.delay_field.setSuffix(" s")
        self.delay_field.setValue(5 if self._wayland else 0)
        self.delay_field.setToolTip(
            "Wait before capturing so you can switch to the game's "
            "workspace or fullscreen window"
        )
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._countdown_tick)
        self._countdown_remaining = 0
        self._countdown_action: Callable[[], None] | None = None
        buttons.addWidget(self.select_button)
        buttons.addWidget(self.preview_button)
        buttons.addStretch()
        buttons.addWidget(QLabel("Delay"))
        buttons.addWidget(self.delay_field)
        region_layout.addLayout(buttons)
        layout.addWidget(region_group)

        preview_group = QGroupBox("Local OCR preview")
        preview_layout = QVBoxLayout(preview_group)
        self.image_preview = QLabel("No screen preview captured")
        self.image_preview.setObjectName("ocrImagePreview")
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setMinimumHeight(170)
        self.image_preview.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        preview_layout.addWidget(self.image_preview, 1)
        self.ocr_text = QLabel("OCR text: —")
        self.ocr_text.setWordWrap(True)
        self.ocr_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        preview_layout.addWidget(self.ocr_text)
        self.validation_status = QLabel("Select an area, then capture a preview.")
        self.validation_status.setObjectName("fieldHint")
        self.validation_status.setWordWrap(True)
        preview_layout.addWidget(self.validation_status)
        layout.addWidget(preview_group, 1)

        supported, reason = self.ocr_engine.support_status()
        if supported:
            capture_ok, capture_reason = self.capture_service.support_status()
            supported = capture_ok
            reason = reason if capture_ok else capture_reason
        support_label = QLabel(reason)
        support_label.setWordWrap(True)
        support_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        support_label.setObjectName("privacyNote" if supported else "fieldHint")
        support_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(support_label)

        # On Linux, list anything this desktop still needs, with the exact
        # install command for the detected distribution.
        missing = detect_environment().missing
        if missing:
            lines = [
                f"<b>{item.title}</b> ({item.purpose}):<br><code>{item.install}</code>"
                for item in missing
            ]
            needs_label = QLabel("Still needed on this system:<br>" + "<br>".join(lines))
            needs_label.setTextFormat(Qt.TextFormat.RichText)
            needs_label.setWordWrap(True)
            needs_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            needs_label.setObjectName("fieldHint")
            layout.addWidget(needs_label)

        dialog_buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        save_button = dialog_buttons.button(QDialogButtonBox.StandardButton.Save)
        if save_button is not None:
            save_button.setText("Save capture area")
        dialog_buttons.accepted.connect(self._accept_region)
        dialog_buttons.rejected.connect(self.reject)
        layout.addWidget(dialog_buttons)

        self._load_region_fields()

    @staticmethod
    def _coordinate_field(minimum: int, maximum: int) -> QSpinBox:
        field = QSpinBox()
        field.setRange(minimum, maximum)
        field.setGroupSeparatorShown(True)
        return field

    def _load_region_fields(self) -> None:
        region = self._region
        if region is None:
            geometry = self.capture_service.virtual_geometry()
            default_width = min(900, max(32, geometry.width() // 2))
            default_height = 100
            region = CaptureRegion(
                geometry.center().x() - default_width // 2,
                geometry.bottom() - default_height - 80,
                default_width,
                default_height,
            )
        self.x_field.setValue(region.x)
        self.y_field.setValue(region.y)
        self.width_field.setValue(region.width)
        self.height_field.setValue(region.height)

    def current_region(self) -> CaptureRegion:
        return CaptureRegion(
            self.x_field.value(),
            self.y_field.value(),
            self.width_field.value(),
            self.height_field.value(),
        )

    def _hide_companion_windows(self) -> None:
        if self._wayland:
            # Re-showing a hidden Wayland window maps it as a new window on
            # the *current* workspace, i.e. behind the game. Leave ordinary
            # windows where they are (the countdown lets the player switch to
            # the game) and only hide overlays, which have no workspace.
            self._windows_to_restore = [
                widget
                for widget in QApplication.topLevelWidgets()
                if widget.isVisible()
                and (
                    getattr(widget, "layer_overlay", None) is not None
                    or getattr(widget, "x11_overlay", False)
                )
                and widget not in self._selectors
            ]
            for widget in self._windows_to_restore:
                widget.hide()
            return
        # Do not hide this modal dialog. QDialog.exec() returns Rejected as soon
        # as its dialog is hidden, which used to discard a freshly selected
        # region before Settings could receive it. Making it fully transparent
        # keeps the modal event loop alive while exposing the pixels underneath.
        self._saved_window_opacity = self.windowOpacity()
        self.setWindowOpacity(0.0)
        self._windows_to_restore = [
            widget
            for widget in QApplication.topLevelWidgets()
            if (
                widget.isVisible()
                and widget is not self
                and widget not in self._selectors
            )
        ]
        for widget in self._windows_to_restore:
            widget.hide()

    def _restore_companion_windows(self) -> None:
        windows = self._windows_to_restore
        self._windows_to_restore = []
        for widget in windows:
            widget.show()
        if self._wayland:
            return
        self.setWindowOpacity(self._saved_window_opacity)
        self.raise_()
        self.activateWindow()

    def _after_countdown(self, action: Callable[[], None]) -> None:
        if self._countdown_timer.isActive():
            return
        self._countdown_action = action
        self._countdown_remaining = self.delay_field.value()
        if self._countdown_remaining <= 0:
            self._finish_countdown()
            return
        self.select_button.setEnabled(False)
        self.preview_button.setEnabled(False)
        self._show_countdown()
        self._countdown_timer.start()

    def _show_countdown(self) -> None:
        self.validation_status.setText(
            "Switch to the game now: capturing in "
            f"{self._countdown_remaining} s…"
        )

    @Slot()
    def _countdown_tick(self) -> None:
        self._countdown_remaining -= 1
        if self._countdown_remaining > 0:
            self._show_countdown()
            return
        self._countdown_timer.stop()
        self._finish_countdown()

    def _finish_countdown(self) -> None:
        action = self._countdown_action
        self._countdown_action = None
        self.select_button.setEnabled(True)
        self.preview_button.setEnabled(not self._preview_busy)
        if action is not None:
            action()

    @Slot()
    def _select_area(self) -> None:
        if self._selectors:
            return
        self._after_countdown(self._begin_selection)

    def _begin_selection(self) -> None:
        if self._selectors:
            return
        self._hide_companion_windows()
        QTimer.singleShot(180, self._show_selectors)

    def _show_selectors(self) -> None:
        if self._wayland:
            # Freeze each monitor first: the selector covers the screen fully.
            try:
                selectors = [
                    ScreenRegionSelector(
                        screen, self.capture_service.capture_screen(screen)
                    )
                    for screen in QApplication.screens()
                ]
            except ScreenCaptureError as exc:
                self._restore_companion_windows()
                self.validation_status.setText(str(exc))
                return
        else:
            selectors = [ScreenRegionSelector()]
        self._selectors = selectors
        for selector in selectors:
            selector.region_selected.connect(self._selection_finished)
            selector.cancelled.connect(self._selection_cancelled)
            selector.present()

    def _close_selectors(self) -> None:
        selectors = self._selectors
        self._selectors = []
        for selector in selectors:
            selector.dispose()

    @Slot(object)
    def _selection_finished(self, region: CaptureRegion) -> None:
        self._close_selectors()
        # Retain the completed selection immediately. The Save button still
        # performs final validation and commits it to application settings.
        self._region = region
        self.x_field.setValue(region.x)
        self.y_field.setValue(region.y)
        self.width_field.setValue(region.width)
        self.height_field.setValue(region.height)
        QTimer.singleShot(180, lambda: self._capture_hidden(region))

    @Slot()
    def _selection_cancelled(self) -> None:
        self._close_selectors()
        self._restore_companion_windows()

    @Slot()
    def _preview_current_area(self) -> None:
        if self._preview_busy:
            return
        region = self.current_region()
        try:
            self.capture_service.validate_region(region)
        except ScreenCaptureError as exc:
            QMessageBox.warning(self, "Invalid capture area", str(exc))
            return
        self._after_countdown(lambda: self._begin_preview(region))

    def _begin_preview(self, region: CaptureRegion) -> None:
        self._hide_companion_windows()
        QTimer.singleShot(220, lambda: self._capture_hidden(region))

    def _capture_hidden(self, region: CaptureRegion) -> None:
        try:
            pixmap = self.capture_service.capture(region)
            png_bytes = self.capture_service.png_bytes_for_ocr(pixmap)
        except ScreenCaptureError as exc:
            self._restore_companion_windows()
            self.validation_status.setText(str(exc))
            return
        self._restore_companion_windows()
        scaled = pixmap.scaled(
            self.image_preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_preview.setPixmap(scaled)
        self.preview_button.setEnabled(False)
        self._preview_busy = True
        self.validation_status.setText(
            f"Reading pixels with {self.ocr_engine.display_name}…"
        )
        worker = _PreviewWorker(self.ocr_engine, png_bytes)
        worker.signals.finished.connect(self._preview_finished)
        self._thread_pool.start(worker)

    @Slot(object, object)
    def _preview_finished(self, text: object, error: object) -> None:
        self._preview_busy = False
        self.preview_button.setEnabled(True)
        if isinstance(error, (OcrUnavailableError, OcrRecognitionError)):
            self.ocr_text.setText("OCR text: —")
            self.validation_status.setText(f"OCR unavailable for this preview: {error}")
            return
        value = str(text or "").strip()
        self.ocr_text.setText(f"OCR text: {value or '—'}")
        try:
            parsed = parse_coordinates_from_ocr(value)
        except CoordinateParseError:
            self.validation_status.setText(
                "No valid coordinate line detected. Adjust the area tightly around the "
                "coordinates and try again."
            )
            return
        self.validation_status.setText(
            f"Valid coordinates detected: {parsed.x:,.3f}, "
            f"{parsed.y:,.3f}, {parsed.z:,.3f}"
        )

    @Slot()
    def _accept_region(self) -> None:
        region = self.current_region()
        try:
            self.capture_service.validate_region(region)
        except ScreenCaptureError as exc:
            QMessageBox.warning(self, "Invalid capture area", str(exc))
            return
        self._region = region
        self.accept()

    @property
    def region(self) -> CaptureRegion:
        assert self._region is not None
        return self._region

    def closeEvent(self, event: QCloseEvent) -> None:
        self._countdown_timer.stop()
        self.ocr_engine.close()
        super().closeEvent(event)

    def done(self, result: int) -> None:
        self._countdown_timer.stop()
        self._countdown_action = None
        self.ocr_engine.close()
        super().done(result)
