"""Pure navigation calculations independent from the UI."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from core.models import Position, Waypoint


CARDINAL_DIRECTIONS = (
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
)

NAMED_POI_LAYERS = (
    "water",
    "locations",
    "food",
    "ai",
    "gastrolith",
    "salt_licks",
    "spawns",
    "custom_markers",
)


@dataclass(frozen=True, slots=True)
class NearestPoi:
    """The closest eligible named point in the editable local map data."""

    name: str
    layer: str
    x: float
    y: float
    distance: float
    heading: float | None


def planar_distance(a: Position | Waypoint, b: Position | Waypoint) -> float:
    """Return two-dimensional world distance between two points."""

    return math.hypot(b.x - a.x, b.y - a.y)


def spatial_distance(a: Position | Waypoint, b: Position | Waypoint) -> float:
    """Return three-dimensional world distance between two points."""

    return math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2 + (b.z - a.z) ** 2)


def heading_degrees(a: Position | Waypoint, b: Position | Waypoint) -> float | None:
    """Return compass heading where north is +Y and east is +X."""

    dx = b.x - a.x
    dy = b.y - a.y
    if math.isclose(dx, 0.0, abs_tol=1e-9) and math.isclose(dy, 0.0, abs_tol=1e-9):
        return None
    return math.degrees(math.atan2(dx, dy)) % 360.0


def cardinal_direction(heading: float | None) -> str:
    if heading is None:
        return "—"
    index = int((heading + 11.25) // 22.5) % 16
    return CARDINAL_DIRECTIONS[index]


def format_distance(world_units: float) -> str:
    """Format Unreal centimetres as metres/kilometres.

    The Isle uses Unreal world units, conventionally centimetres. Calibration
    can still be changed independently of this display convention.
    """

    metres = world_units / 100.0
    return f"{metres / 1000.0:.2f} km" if metres >= 1000.0 else f"{metres:.0f} m"


def nearest_named_poi(
    player: Position,
    layers: Mapping[str, Sequence[Mapping[str, Any]]],
    enabled_layers: Mapping[str, Any],
) -> NearestPoi | None:
    """Find the nearest visible point that is intended to have a name label.

    Editable data can contain placeholder or malformed records. They are skipped
    here just as they are by the renderer. Layer order followed by source order
    provides deterministic tie-breaking.
    """

    nearest: NearestPoi | None = None
    for layer_name in NAMED_POI_LAYERS:
        if not bool(enabled_layers.get(layer_name, True)):
            continue
        for item in layers.get(layer_name, ()):
            if item.get("show_label", True) is False:
                continue
            name_value = item.get("name")
            if not isinstance(name_value, str) or not name_value.strip():
                continue
            try:
                item_position = item["position"]
                x = float(item_position[0])
                y = float(item_position[1])
            except (KeyError, TypeError, ValueError, IndexError):
                continue
            if not math.isfinite(x) or not math.isfinite(y):
                continue
            dx = x - player.x
            dy = y - player.y
            distance = math.hypot(dx, dy)
            if nearest is not None and distance >= nearest.distance:
                continue
            heading = None
            if not (
                math.isclose(dx, 0.0, abs_tol=1e-9)
                and math.isclose(dy, 0.0, abs_tol=1e-9)
            ):
                heading = math.degrees(math.atan2(dx, dy)) % 360.0
            nearest = NearestPoi(
                name=name_value.strip(),
                layer=layer_name,
                x=x,
                y=y,
                distance=distance,
                heading=heading,
            )
    return nearest
