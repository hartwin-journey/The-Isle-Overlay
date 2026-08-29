"""Render a deterministic off-screen UI preview for development QA."""

from __future__ import annotations

import copy
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QTabWidget

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.app_state import AppState
from core.coordinate_transform import load_calibration
from core.data_loader import LayerRepository
from core.models import Position, Waypoint
from core.settings import DEFAULT_SETTINGS, SettingsStore
from ui.main_window import MainWindow
from ui.mini_map import MiniMapWindow
from ui.ocr_setup_window import OcrSetupDialog
from ui.settings_window import SettingsWindow
from ui.styles import DARK_STYLESHEET


def main() -> int:
    app = QApplication([])
    app.setStyleSheet(DARK_STYLESHEET)
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    store = SettingsStore(PROJECT_ROOT / "config" / "settings.json")
    store.values = settings
    calibration = load_calibration(PROJECT_ROOT / "map" / "calibration.json")
    repository = LayerRepository(PROJECT_ROOT / "data")
    state = AppState(settings)
    window = MainWindow(PROJECT_ROOT, store, calibration, repository, state)
    mini_map = MiniMapWindow(
        PROJECT_ROOT / "map" / "gateway.webp",
        calibration,
        repository,
        state,
    )
    window.attach_mini_map(mini_map)
    window.resize(1280, 820)
    window.show()
    mini_map.show()
    state.update_position(Position(22000, 52000, 3200, datetime.now(timezone.utc)))
    state.update_position(Position(42000, 76000, 3350, datetime.now(timezone.utc)))
    state.set_waypoint(Waypoint("Rally point", 145000, 165000, 0))
    settings_window = SettingsWindow(settings, calibration, PROJECT_ROOT)
    settings_window.show()
    ocr_setup = OcrSetupDialog(settings, PROJECT_ROOT)
    ocr_setup.show()

    output = PROJECT_ROOT / "logs" / "ui-preview.png"
    zone_output = PROJECT_ROOT / "logs" / "zone-preview.png"
    settings_output = PROJECT_ROOT / "logs" / "settings-preview.png"
    settings_map_output = PROJECT_ROOT / "logs" / "settings-map-preview.png"
    mini_output = PROJECT_ROOT / "logs" / "mini-map-preview.png"
    mini_circle_output = PROJECT_ROOT / "logs" / "mini-map-circle-preview.png"
    ocr_setup_output = PROJECT_ROOT / "logs" / "ocr-setup-preview.png"

    def capture() -> None:
        window.grab().save(str(output))
        mini_map.grab().save(str(mini_output))
        state.settings["overlay_shape"] = "circle"
        mini_map.apply_settings()
        app.processEvents()
        mini_map.grab().save(str(mini_circle_output))
        state.settings["layers"]["patrol_zones"] = True
        state.layers_changed.emit()
        app.processEvents()
        window.grab().save(str(zone_output))
        settings_window.grab().save(str(settings_output))
        ocr_setup.grab().save(str(ocr_setup_output))
        tabs = settings_window.findChild(QTabWidget)
        if tabs is not None:
            tabs.setCurrentIndex(1)
            app.processEvents()
            settings_window.grab().save(str(settings_map_output))
        app.quit()

    QTimer.singleShot(500, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
