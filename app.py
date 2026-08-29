"""The Isle Companion entry point.

Security boundary: coordinates come only from ordinary Windows clipboard text
or an optional user-selected rectangle captured through normal screen pixels.
This application never opens or inspects The Isle, Steam, Easy Anti-Cheat,
game memory, game files, renderer state, or network traffic, and never sends
input to the game.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from core.app_state import AppState
from core.automatic_tracking import AutomaticCoordinateTracker
from core.clipboard_monitor import ClipboardCoordinateMonitor
from core.coordinate_transform import load_calibration
from core.data_loader import LayerRepository
from core.hotkeys import GlobalHotkeyManager
from core.local_ocr import OcrUnavailableError, WindowsOcrEngine
from core.models import Position
from core.overlay_interaction import ToggleInputMonitor
from core.screen_capture import CaptureRegion, ScreenCaptureError
from core.settings import SettingsStore
from ui.main_window import MainWindow
from ui.mini_map import MiniMapWindow
from ui.styles import DARK_STYLESHEET

LOGGER = logging.getLogger(__name__)


def configure_logging(project_root: Path) -> None:
    log_folder = project_root / "logs"
    log_folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_folder / "companion.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def create_app_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#102d38"))
    painter.setPen(QColor("#42d2ea"))
    painter.drawEllipse(3, 3, 58, 58)
    painter.setPen(QColor("#eafcff"))
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(28)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "IC")
    painter.end()
    return QIcon(pixmap)


class ApplicationController:
    def __init__(self, app: QApplication, project_root: Path) -> None:
        self.app = app
        self.project_root = project_root
        self.settings_store = SettingsStore(project_root / "config" / "settings.json")
        settings = self.settings_store.load()
        calibration = load_calibration(project_root / "map" / "calibration.json")
        data_folder = Path(str(settings["data_folder"]))
        if not data_folder.is_absolute():
            data_folder = project_root / data_folder
        self.repository = LayerRepository(
            data_folder,
            custom_markers_path=project_root / "config" / "custom_markers.json",
        )
        self.state = AppState(settings)

        self.main_window = MainWindow(
            project_root,
            self.settings_store,
            calibration,
            self.repository,
            self.state,
        )
        self.mini_map = MiniMapWindow(
            project_root / "map" / "gateway.webp",
            calibration,
            self.repository,
            self.state,
        )
        self.main_window.attach_mini_map(self.mini_map)
        self.main_window.hotkeys_changed.connect(self.restart_hotkeys)
        self.main_window.automatic_tracking_changed.connect(
            self.set_automatic_tracking
        )
        self.main_window.exit_requested.connect(self.shutdown)

        # Manual tracking remains available independently of optional OCR.
        self.clipboard_monitor = ClipboardCoordinateMonitor(app.clipboard())
        self.clipboard_monitor.position_copied.connect(self._handle_clipboard_position)

        self.automatic_tracker = AutomaticCoordinateTracker(
            WindowsOcrEngine(project_root / "core" / "windows_ocr.ps1"),
            parent=self.app,
        )
        self.automatic_tracker.position_detected.connect(self._handle_automatic_position)
        self.automatic_tracker.status_changed.connect(
            lambda status: self.main_window.set_automatic_tracking_status(
                self.automatic_tracker.enabled,
                status,
            )
        )
        self.automatic_tracker.unavailable.connect(
            self._automatic_tracking_unavailable
        )

        self.tray_icon: QSystemTrayIcon | None = None
        self._configure_tray()
        self.overlay_interaction_monitor = ToggleInputMonitor(
            str(self.state.settings["overlay_interaction_hold_key"]),
            parent=self.app,
        )
        self.overlay_interaction_monitor.toggled_changed.connect(
            self.mini_map.set_interaction_enabled
        )
        self.overlay_interaction_monitor.binding_error.connect(
            lambda reason: self.main_window.statusBar().showMessage(
                f"Mini Map interaction binding unavailable: {reason}", 5000
            )
        )
        self.overlay_interaction_monitor.start()
        self.hotkey_manager: GlobalHotkeyManager | None = None
        self.restart_hotkeys()

    def _handle_clipboard_position(self, position: Position) -> None:
        self.state.update_position(position)
        self.main_window.clipboard_status.setText("Valid copied coordinates received")

    def _handle_automatic_position(self, position: Position) -> None:
        self.state.update_position(position)

    def _automatic_tracking_unavailable(self, reason: str) -> None:
        self.state.settings["automatic_tracking_enabled"] = False
        self.settings_store.save()
        self.main_window.set_automatic_tracking_status(
            False,
            f"Automatic tracking unavailable: {reason}",
        )

    def set_automatic_tracking(self, enabled: bool) -> None:
        if not enabled:
            self.automatic_tracker.stop()
            self.main_window.set_automatic_tracking_status(
                False,
                "Automatic tracking: off",
            )
            return
        region = CaptureRegion.from_mapping(
            self.state.settings.get("automatic_tracking_region")
        )
        if region is None:
            self._automatic_tracking_unavailable("capture area is not configured")
            return
        try:
            self.automatic_tracker.start(
                region,
                interval_ms=int(
                    self.state.settings["automatic_tracking_interval_ms"]
                ),
                confirmation_reads=int(
                    self.state.settings["automatic_tracking_confirmation_reads"]
                ),
            )
        except (OcrUnavailableError, ScreenCaptureError) as exc:
            self._automatic_tracking_unavailable(str(exc))

    def _configure_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.app.setQuitOnLastWindowClosed(True)
            return
        self.app.setQuitOnLastWindowClosed(False)
        tray = QSystemTrayIcon(create_app_icon(), self.app)
        tray.setToolTip("The Isle Companion")
        menu = QMenu()
        show_full = QAction("Show Full Map", menu)
        show_full.triggered.connect(self.main_window.toggle_full_map)
        show_mini = QAction("Show Mini Map", menu)
        show_mini.triggered.connect(self.main_window.toggle_mini_map)
        quit_action = QAction("Exit", menu)
        quit_action.triggered.connect(self.shutdown)
        menu.addAction(show_full)
        menu.addAction(show_mini)
        menu.addSeparator()
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(
            lambda reason: self.main_window.toggle_full_map()
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick
            else None
        )
        tray.show()
        self.tray_icon = tray
        self.main_window.tray_available = True

    def restart_hotkeys(self) -> None:
        if hasattr(self, "overlay_interaction_monitor"):
            self.overlay_interaction_monitor.set_binding(
                str(self.state.settings["overlay_interaction_hold_key"])
            )
        if self.hotkey_manager is not None:
            self.hotkey_manager.stop()
            self.hotkey_manager.deleteLater()
        self.hotkey_manager = GlobalHotkeyManager(self.state.settings["hotkeys"])
        self.hotkey_manager.activated.connect(self._handle_hotkey)
        self.hotkey_manager.registration_failed.connect(
            lambda action, reason: self.main_window.statusBar().showMessage(
                f"Hotkey unavailable ({action}): {reason}", 5000
            )
        )
        self.hotkey_manager.start()

    def _handle_hotkey(self, action: str) -> None:
        callbacks = {
            "toggle_full_map": self.main_window.toggle_full_map,
            "toggle_mini_map": self.main_window.toggle_mini_map,
            "toggle_layer_panel": self.main_window.toggle_layer_panel,
            "toggle_breadcrumbs": self.main_window.toggle_breadcrumbs,
            "clear_waypoint": self.main_window.clear_waypoint,
            "recenter_player": self.main_window.recenter_player,
            "toggle_player_centered": self.main_window.toggle_player_centered,
            "increase_opacity": lambda: self.main_window.change_overlay_opacity(0.05),
            "decrease_opacity": lambda: self.main_window.change_overlay_opacity(-0.05),
        }
        callback = callbacks.get(action)
        if callback:
            callback()

    def start(self) -> None:
        self.main_window.show()
        if self.state.settings["launch_mini_map_on_startup"]:
            self.mini_map.show()
        self.set_automatic_tracking(
            bool(self.state.settings["automatic_tracking_enabled"])
        )

    def shutdown(self) -> None:
        LOGGER.info("Application shutdown")
        if self.hotkey_manager is not None:
            self.hotkey_manager.stop()
        self.overlay_interaction_monitor.stop()
        self.automatic_tracker.close()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self.app.quit()


def main() -> int:
    project_root = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )
    configure_logging(project_root)
    LOGGER.info("Application startup")
    app = QApplication(sys.argv)
    app.setApplicationName("The Isle Companion")
    app.setOrganizationName("Local")
    app.setWindowIcon(create_app_icon())
    app.setStyleSheet(DARK_STYLESHEET)
    controller = ApplicationController(app, project_root)
    controller.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
