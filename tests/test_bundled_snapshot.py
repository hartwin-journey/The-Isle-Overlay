import json
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QImageReader


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _items(filename: str) -> list[dict[str, object]]:
    with (PROJECT_ROOT / "data" / filename).open("r", encoding="utf-8") as handle:
        return json.load(handle)["items"]


def test_gateway_rasters_match_when_private_local_images_are_present():
    base_path = PROJECT_ROOT / "map" / "gateway.webp"
    water_path = PROJECT_ROOT / "map" / "gateway_water.webp"
    if not base_path.exists():
        # The private-use rasters are deliberately absent from a clean Git
        # checkout; the application uses its generated fallback in that case.
        assert not water_path.exists()
        return

    base = QImageReader(str(base_path))
    assert base.canRead()
    assert base.size() == QSize(7800, 7817)
    if water_path.exists():
        water = QImageReader(str(water_path))
        assert water.canRead()
        assert water.size() == base.size()


def test_gateway_snapshot_layer_counts():
    expected = {
        "migrations.json": 12,
        "patrol_zones.json": 20,
        "sanctuaries.json": 8,
        "updrafts.json": 21,
        "water.json": 27,
        "locations.json": 74,
        "food.json": 266,
        "ai.json": 750,
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
