import copy
from datetime import datetime, timezone

from core.app_state import AppState
from core.map_fonts import (
    DEFAULT_MAP_LABEL_FONT_PRESET,
    MAP_LABEL_FONT_PRESETS,
    get_map_label_font_preset,
)
from core.models import Position, Waypoint
from core.settings import DEFAULT_SETTINGS


def _position(x: float, y: float, z: float = 0.0) -> Position:
    return Position(x, y, z, datetime.now(timezone.utc))


def test_app_state_tracks_distinct_positions_breadcrumbs_and_waypoint_signals():
    state = AppState(copy.deepcopy(DEFAULT_SETTINGS))
    positions = []
    breadcrumb_events = []
    waypoint_events = []
    state.position_changed.connect(lambda current, previous: positions.append((current, previous)))
    state.breadcrumbs_changed.connect(lambda: breadcrumb_events.append(True))
    state.waypoint_changed.connect(waypoint_events.append)

    first = _position(10, 20, 30)
    second = _position(110, 20, 30)
    state.update_position(first)
    state.update_position(first)
    state.update_position(second)

    assert positions == [(first, None), (second, first)]
    assert list(state.breadcrumbs) == [first, second]
    assert len(breadcrumb_events) == 2
    assert state.last_movement_heading is not None
    assert state.last_movement_distance == 100

    waypoint = Waypoint("Home", 1, 2, 3)
    state.set_waypoint(waypoint)
    state.clear_breadcrumbs()
    assert waypoint_events == [waypoint]
    assert not state.breadcrumbs


def test_app_state_respects_disabled_breadcrumbs_and_applies_new_limit():
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    settings["breadcrumbs_enabled"] = False
    state = AppState(settings)
    state.update_position(_position(1, 1))
    assert not state.breadcrumbs

    state.settings["breadcrumbs_enabled"] = True
    state.update_position(_position(2, 2))
    state.update_position(_position(3, 3))
    state.apply_breadcrumb_limit(1)
    assert len(state.breadcrumbs) == 1
    assert state.breadcrumbs[0].x == 3


def test_models_serialize_and_font_presets_have_a_safe_fallback():
    timestamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    position = Position(1, 2, 3, timestamp)
    waypoint = Waypoint.from_dict({"name": "Lake", "x": "4.5", "y": 6})

    assert position.to_dict()["timestamp"] == "2026-01-02T03:04:05+00:00"
    assert waypoint == Waypoint("Lake", 4.5, 6.0, 0.0)
    assert waypoint.to_dict()["name"] == "Lake"
    assert get_map_label_font_preset("verdana_bold") == MAP_LABEL_FONT_PRESETS["verdana_bold"]
    assert get_map_label_font_preset(object()) == MAP_LABEL_FONT_PRESETS[
        DEFAULT_MAP_LABEL_FONT_PRESET
    ]
