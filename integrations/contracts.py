"""Stable map identity and connection configuration contracts."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

LOGGER = logging.getLogger(__name__)

PROTOCOL_NAME = "tic"
PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 65_536
MAX_TEXT_LENGTH = 256
CAPABILITY_POSITION_PUBLISH = "position.publish"
CAPABILITY_WAYPOINT_PUBLISH = "waypoint.publish"
CAPABILITY_POINTS_SUBSCRIBE = "points.subscribe"
KNOWN_CAPABILITIES = frozenset(
    {
        CAPABILITY_POSITION_PUBLISH,
        CAPABILITY_WAYPOINT_PUBLISH,
        CAPABILITY_POINTS_SUBSCRIBE,
    }
)

DEFAULT_MAP_IDENTITY: "MapIdentity"


class IntegrationConfigurationError(ValueError):
    """Raised when an enabled connection profile is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class MapIdentity:
    game: str
    id: str
    display_name: str
    map_version: str
    coordinate_space: str
    units: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MapIdentity":
        identity = cls(
            game=_required_text(value, "game"),
            id=_required_text(value, "id"),
            display_name=_required_text(value, "display_name"),
            map_version=_required_text(value, "map_version"),
            coordinate_space=_required_text(value, "coordinate_space"),
            units=_required_text(value, "units"),
        )
        return identity

    def to_protocol_dict(self) -> dict[str, str]:
        return {
            "game": self.game,
            "id": self.id,
            "version": self.map_version,
            "coordinate_space": self.coordinate_space,
            "units": self.units,
        }


DEFAULT_MAP_IDENTITY = MapIdentity(
    game="the-isle-evrima",
    id="gateway",
    display_name="Gateway",
    map_version="0.21.772",
    coordinate_space="the-isle-world-v1",
    units="game-world-units",
)


def _required_text(value: dict[str, Any], key: str) -> str:
    text = str(value.get(key, "")).strip()
    if not text or len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"map manifest {key} is missing or too long")
    return text


def load_map_identity(path: Path) -> MapIdentity:
    """Load bundled map identity, with the same safe fallback style as calibration."""

    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise TypeError("map manifest root must be an object")
        return MapIdentity.from_dict(value)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        LOGGER.error("Configuration error loading map manifest: %s", exc)
        return DEFAULT_MAP_IDENTITY


def validate_websocket_url(value: str) -> str:
    """Allow encrypted remote sockets and explicitly local development sockets."""

    text = str(value).strip()
    if len(text) > 2_048:
        raise IntegrationConfigurationError("WebSocket URL is too long")
    parsed = urlsplit(text)
    if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
        raise IntegrationConfigurationError("Enter a complete ws:// or wss:// WebSocket URL")
    if parsed.username or parsed.password:
        raise IntegrationConfigurationError(
            "Do not place credentials in the URL; use the access token field"
        )
    local_hosts = {"127.0.0.1", "::1", "localhost"}
    if parsed.scheme == "ws" and parsed.hostname.casefold() not in local_hosts:
        raise IntegrationConfigurationError(
            "Remote integrations must use encrypted wss://; ws:// is allowed only on this computer"
        )
    return text


_ROOM_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_room(value: str) -> str:
    room = str(value).strip()
    if not _ROOM_PATTERN.fullmatch(room):
        raise IntegrationConfigurationError(
            "Room must be 1–64 letters, numbers, dots, underscores, or hyphens"
        )
    return room
