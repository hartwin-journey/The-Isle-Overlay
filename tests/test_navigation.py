from datetime import datetime, timezone

import pytest

from core.models import Position
from core.navigation import (
    cardinal_direction,
    heading_degrees,
    nearest_named_poi,
    planar_distance,
)


def position(x, y, z=0):
    return Position(x, y, z, datetime.now(timezone.utc))


@pytest.mark.parametrize(
    ("target", "heading", "direction"),
    [
        ((0, 10), 0, "N"),
        ((10, 0), 90, "E"),
        ((0, -10), 180, "S"),
        ((-10, 0), 270, "W"),
        ((10, 10), 45, "NE"),
    ],
)
def test_heading(target, heading, direction):
    result = heading_degrees(position(0, 0), position(*target))
    assert result == pytest.approx(heading)
    assert cardinal_direction(result) == direction


def test_planar_distance_ignores_altitude():
    assert planar_distance(position(0, 0, 500), position(300, 400, 900)) == 500


def test_nearest_named_poi_uses_only_visible_intentionally_labeled_points():
    layers = {
        "locations": [
            {"name": "Hidden landmark", "position": [1, 0]},
            {"name": "Visible landmark", "position": [300, 400]},
            {"name": "Malformed", "position": ["not-a-number", 0]},
        ],
        "water": [
            {"name": "Unlabeled pond", "position": [2, 0], "show_label": False},
            {"name": "North pond", "position": [0, 1000]},
        ],
        "ai": [{"name": "Boar 1", "position": [3, 0], "show_label": False}],
    }
    result = nearest_named_poi(
        position(0, 0),
        layers,
        {"locations": False, "water": True, "ai": True},
    )

    assert result is not None
    assert result.name == "North pond"
    assert result.layer == "water"
    assert result.distance == 1000
    assert result.heading == 0


def test_nearest_named_poi_ties_are_deterministic_and_invalid_records_are_safe():
    layers = {
        "water": [
            {"name": "First", "position": [100, 0]},
            {"name": "Second", "position": [-100, 0]},
            {"name": "", "position": [0, 0]},
            {"position": [0, 0]},
            {"name": "Infinite", "position": [float("inf"), 0]},
        ]
    }

    result = nearest_named_poi(position(0, 0), layers, {"water": True})

    assert result is not None
    assert result.name == "First"
    assert result.heading == 90
    assert nearest_named_poi(position(0, 0), layers, {"water": False}) is None
