import hashlib
import json
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QImageReader


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _items(filename: str) -> list[dict[str, object]]:
    with (PROJECT_ROOT / "data" / filename).open("r", encoding="utf-8") as handle:
        return json.load(handle)["items"]


def test_gateway_rasters_are_bundled_matching_full_resolution_images():
    base_path = PROJECT_ROOT / "assets" / "map" / "gateway.webp"
    water_path = PROJECT_ROOT / "assets" / "map" / "gateway_water.webp"
    base = QImageReader(str(base_path))
    water = QImageReader(str(water_path))
    assert base.canRead()
    assert water.canRead()
    assert base.size() == QSize(7800, 7817)
    assert water.size() == base.size()
    assert hashlib.sha256(base_path.read_bytes()).hexdigest() == (
        "ba2e5e614995bec84559b950f1ae978c2f9a66743f0da47a348278db01557ef3"
    )
    assert hashlib.sha256(water_path.read_bytes()).hexdigest() == (
        "301cc51b39e0d26bf8ee25dbf3b72e1d28993b2025548de9ce924e6d800a0032"
    )


def test_gateway_calibration_is_bundled_for_the_exact_raster():
    calibration_path = PROJECT_ROOT / "assets" / "map" / "calibration.json"
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    assert calibration["world_bounds"] == {
        "min_x": -607000.0,
        "max_x": 509000.0,
        "min_y": -505000.0,
        "max_y": 607000.0,
    }
    assert calibration["pixel_bounds"] == {
        "min_x": 0.0,
        "max_x": 7800.0,
        "min_y": 0.0,
        "max_y": 7817.0,
    }
    assert calibration["swap_axes"] is True
    assert hashlib.sha256(calibration_path.read_bytes()).hexdigest() == (
        "55e42649a30c28295fc7fb304c21403d9271535c116c1aafbaab3dc78c02036b"
    )


def test_gateway_snapshot_layer_counts():
    expected = {
        "migrations.json": 12,
        "patrol_zones.json": 20,
        "sanctuaries.json": 8,
        "updrafts.json": 21,
        "water.json": 27,
        "locations.json": 74,
        "food.json": 266,
        "ai.json": 507,
        "gastrolith.json": 243,
        "salt_licks.json": 24,
    }
    for filename, count in expected.items():
        items = _items(filename)
        assert len(items) == count
        assert all(not str(item.get("name", "")).startswith("Example") for item in items)


def test_gateway_zone_palette_matches_vulnona_snapshot():
    assert {item.get("color") for item in _items("migrations.json")} == {"#00CC77"}
    assert {item.get("color") for item in _items("patrol_zones.json")} == {"#FF0000"}
    assert {item.get("color") for item in _items("sanctuaries.json")} == {"#FF99FF"}


def test_gateway_updraft_snapshot_is_complete_and_unique():
    items = _items("updrafts.json")
    assert len(items) == 21
    assert len({item["source_id"] for item in items}) == 21
    assert len({tuple(item["position"]) for item in items}) == 21
    assert all(item.get("show_label") is False for item in items)
    assert all(item.get("active_hours") for item in items)
    assert all(
        -607_000 <= item["position"][0] <= 509_000
        and -505_000 <= item["position"][1] <= 607_000
        for item in items
    )
