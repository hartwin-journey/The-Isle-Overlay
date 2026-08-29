"""In-memory application state shared by the full map and mini map."""

from __future__ import annotations

from collections import deque
from typing import Any

from PySide6.QtCore import QObject, Signal

from core.models import Position, Waypoint
from core.navigation import heading_degrees, planar_distance


class AppState(QObject):
    position_changed = Signal(object, object)
    breadcrumbs_changed = Signal()
    waypoint_changed = Signal(object)
    layers_changed = Signal()
    settings_changed = Signal()

    def __init__(self, settings: dict[str, Any]) -> None:
        super().__init__()
        self.settings = settings
        self.current_position: Position | None = None
        self.previous_position: Position | None = None
        self.breadcrumbs: deque[Position] = deque(
            maxlen=int(settings["breadcrumb_max_points"])
        )
        self.active_waypoint: Waypoint | None = None
        self.last_movement_heading: float | None = None
        self.last_movement_distance: float = 0.0

    def update_position(self, position: Position) -> None:
        if self.current_position is not None:
            if (
                position.x == self.current_position.x
                and position.y == self.current_position.y
                and position.z == self.current_position.z
            ):
                return
            self.previous_position = self.current_position
            self.last_movement_heading = heading_degrees(self.previous_position, position)
            self.last_movement_distance = planar_distance(self.previous_position, position)
        self.current_position = position
        if self.settings["breadcrumbs_enabled"]:
            self.breadcrumbs.append(position)
            self.breadcrumbs_changed.emit()
        self.position_changed.emit(self.current_position, self.previous_position)

    def set_waypoint(self, waypoint: Waypoint | None) -> None:
        self.active_waypoint = waypoint
        self.waypoint_changed.emit(waypoint)

    def clear_breadcrumbs(self) -> None:
        self.breadcrumbs.clear()
        self.breadcrumbs_changed.emit()

    def apply_breadcrumb_limit(self, maximum: int) -> None:
        existing = list(self.breadcrumbs)[-maximum:]
        self.breadcrumbs = deque(existing, maxlen=maximum)
        self.breadcrumbs_changed.emit()

