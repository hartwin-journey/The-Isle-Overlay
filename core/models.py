"""Shared data models used by the UI and coordinate services."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class Position:
    """A world-space position copied from The Isle by the user."""

    x: float
    y: float
    z: float
    timestamp: datetime

    @classmethod
    def now(cls, x: float, y: float, z: float) -> "Position":
        return cls(x=x, y=y, z=z, timestamp=datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        return result


@dataclass(frozen=True, slots=True)
class Waypoint:
    """A named world-space waypoint."""

    name: str
    x: float
    y: float
    z: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Waypoint":
        return cls(
            name=str(value.get("name", "Waypoint")),
            x=float(value["x"]),
            y=float(value["y"]),
            z=float(value.get("z", 0.0)),
        )

