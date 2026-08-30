"""In-memory external map points, kept separate from local saved layers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True, slots=True)
class ExternalPointFeature:
    connection_id: str
    feature_id: str
    kind: str
    name: str
    x: float
    y: float
    z: float = 0.0
    description: str = ""
    color: str | None = None
    expires_at: datetime | None = None


class OverlayStore(QObject):
    """Own ephemeral features supplied by optional adapters."""

    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._features: dict[tuple[str, str], ExternalPointFeature] = {}

    @property
    def features(self) -> tuple[ExternalPointFeature, ...]:
        return tuple(self._features.values())

    def upsert(self, feature: ExternalPointFeature) -> None:
        key = (feature.connection_id, feature.feature_id)
        if self._features.get(key) == feature:
            return
        self._features[key] = feature
        self.changed.emit()

    def remove(self, connection_id: str, feature_id: str) -> None:
        if self._features.pop((connection_id, feature_id), None) is not None:
            self.changed.emit()

    def clear_connection(self, connection_id: str) -> None:
        keys = [key for key in self._features if key[0] == connection_id]
        if not keys:
            return
        for key in keys:
            self._features.pop(key, None)
        self.changed.emit()

    def clear(self) -> None:
        if self._features:
            self._features.clear()
            self.changed.emit()

    def prune_expired(self, now: datetime | None = None) -> int:
        current = now or datetime.now(timezone.utc)
        keys = [
            key
            for key, feature in self._features.items()
            if feature.expires_at is not None and feature.expires_at <= current
        ]
        for key in keys:
            self._features.pop(key, None)
        if keys:
            self.changed.emit()
        return len(keys)
