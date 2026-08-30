import copy
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.app_state import AppState
from core.coordinate_transform import load_calibration
from core.data_loader import LayerRepository
from core.overlay_store import ExternalPointFeature, OverlayStore
from core.settings import DEFAULT_SETTINGS
from ui.map_canvas import MapCanvas


def test_map_canvas_renders_and_clears_external_points():
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    state = AppState(settings)
    overlays = OverlayStore()
    canvas = MapCanvas(
        root / "map" / "gateway.webp",
        load_calibration(root / "map" / "calibration.json"),
        LayerRepository(root / "data"),
        state,
        overlays,
    )
    overlays.upsert(
        ExternalPointFeature(
            connection_id="test",
            feature_id="player:friend",
            kind="player",
            name="Friend",
            x=1000,
            y=2000,
        )
    )
    app.processEvents()

    assert len(canvas._groups["external"].childItems()) == 2
    overlays.clear_connection("test")
    app.processEvents()
    assert canvas._groups["external"].childItems() == []
