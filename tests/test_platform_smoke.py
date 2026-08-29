import copy
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QToolBar

from app import ApplicationController
from core.settings import DEFAULT_SETTINGS


def test_controller_starts_without_windows_only_services(tmp_path):
    app = QApplication.instance() or QApplication([])
    controller = ApplicationController(
        app,
        tmp_path,
        windows_features=False,
    )

    assert controller.automatic_tracker is None
    assert controller.overlay_interaction_monitor is None
    assert controller.hotkey_manager is None
    assert controller.state.settings["automatic_tracking_enabled"] is False
    toolbar = controller.main_window.findChild(QToolBar, "mainToolbar")
    assert toolbar is not None
    assert controller.main_window.mini_map_edit_action in toolbar.actions()
    assert controller.main_window.automatic_tracking_action not in toolbar.actions()

    controller.shutdown()
    app.processEvents()


def test_linux_startup_disables_a_stale_automatic_tracking_setting(tmp_path):
    config_folder = tmp_path / "config"
    config_folder.mkdir()
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    settings["automatic_tracking_enabled"] = True
    (config_folder / "settings.json").write_text(
        json.dumps(settings),
        encoding="utf-8",
    )
    app = QApplication.instance() or QApplication([])

    controller = ApplicationController(
        app,
        tmp_path,
        windows_features=False,
    )

    assert controller.state.settings["automatic_tracking_enabled"] is False
    controller.shutdown()
    app.processEvents()
