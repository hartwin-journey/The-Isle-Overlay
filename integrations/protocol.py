"""Versioned JSON codec and strict validation for The Isle Companion protocol."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
import re
from typing import Any
from uuid import uuid4

from core.overlay_store import ExternalPointFeature
from integrations.contracts import (
    KNOWN_CAPABILITIES,
    MAX_MESSAGE_BYTES,
    MAX_TEXT_LENGTH,
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    MapIdentity,
    validate_room,
)

KNOWN_MESSAGE_TYPES = frozenset(
    {
        "hello",
        "welcome",
        "position.update",
        "waypoint.upsert",
        "waypoint.clear",
        "feature.upsert",
        "feature.remove",
        "ping",
        "pong",
        "error",
    }
)
FEATURE_KINDS = frozenset({"player", "waypoint", "marker"})
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ProtocolError(ValueError):
    """Raised when a remote message is unsupported, unsafe, or malformed."""


@dataclass(frozen=True, slots=True)
class ProtocolMessage:
    type: str
    message_id: str
    sent_at: datetime
    payload: dict[str, Any]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_timestamp(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc)
    return normalized.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_timestamp(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise ProtocolError(f"{field_name} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProtocolError(f"{field_name} must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ProtocolError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def encode_message(
    message_type: str,
    payload: dict[str, Any],
    map_identity: MapIdentity,
    *,
    message_id: str | None = None,
    sent_at: datetime | None = None,
) -> str:
    if message_type not in KNOWN_MESSAGE_TYPES:
        raise ProtocolError(f"unsupported message type: {message_type}")
    if not isinstance(payload, dict):
        raise ProtocolError("payload must be an object")
    value = {
        "protocol": PROTOCOL_NAME,
        "version": PROTOCOL_VERSION,
        "type": message_type,
        "message_id": message_id or str(uuid4()),
        "sent_at": format_timestamp(sent_at or utc_now()),
        "map": map_identity.to_protocol_dict(),
        "payload": payload,
    }
    encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ProtocolError("message exceeds the 64 KiB limit")
    return encoded


def decode_message(raw: str, expected_map: MapIdentity) -> ProtocolMessage:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ProtocolError("message exceeds the 64 KiB limit or is not text")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError("message is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ProtocolError("message root must be an object")
    if value.get("protocol") != PROTOCOL_NAME or value.get("version") != PROTOCOL_VERSION:
        raise ProtocolError("unsupported protocol name or version")
    message_type = value.get("type")
    if message_type not in KNOWN_MESSAGE_TYPES:
        raise ProtocolError("unsupported message type")
    message_id = _identifier(value.get("message_id"), "message_id")
    sent_at = parse_timestamp(value.get("sent_at"), "sent_at")
    map_value = value.get("map")
    if not isinstance(map_value, dict):
        raise ProtocolError("map must be an object")
    expected = expected_map.to_protocol_dict()
    for key in ("game", "id", "version", "coordinate_space", "units"):
        if map_value.get(key) != expected[key]:
            raise ProtocolError(f"map {key} does not match this companion build")
    payload = value.get("payload")
    if not isinstance(payload, dict):
        raise ProtocolError("payload must be an object")
    return ProtocolMessage(message_type, message_id, sent_at, payload)


def parse_capabilities(value: Any) -> frozenset[str]:
    if not isinstance(value, list) or len(value) > len(KNOWN_CAPABILITIES):
        raise ProtocolError("capabilities must be a short array")
    capabilities = frozenset(str(item) for item in value)
    if not capabilities.issubset(KNOWN_CAPABILITIES):
        raise ProtocolError("capabilities contain an unsupported value")
    return capabilities


def parse_hello_payload(payload: dict[str, Any]) -> tuple[str, str, frozenset[str]]:
    room = validate_room(str(payload.get("room", "")))
    display_name = _text(payload.get("display_name", "Player"), "display_name", required=True)
    capabilities = parse_capabilities(payload.get("capabilities"))
    return room, display_name, capabilities


def parse_welcome_payload(payload: dict[str, Any]) -> tuple[str, frozenset[str]]:
    session_id = _identifier(payload.get("session_id"), "session_id")
    capabilities = parse_capabilities(payload.get("capabilities"))
    return session_id, capabilities


def parse_position_payload(payload: dict[str, Any]) -> tuple[float, float, float, datetime]:
    position = payload.get("position")
    if not isinstance(position, dict):
        raise ProtocolError("position must be an object")
    x, y, z = _position(position)
    observed_at = parse_timestamp(position.get("observed_at"), "position.observed_at")
    return x, y, z, observed_at


def parse_waypoint_payload(payload: dict[str, Any]) -> tuple[str, float, float, float]:
    waypoint = payload.get("waypoint")
    if not isinstance(waypoint, dict):
        raise ProtocolError("waypoint must be an object")
    name = _text(waypoint.get("name"), "waypoint.name", required=True)
    x, y, z = _position(waypoint.get("position"))
    return name, x, y, z


def parse_remote_feature(
    payload: dict[str, Any],
    connection_id: str,
    *,
    now: datetime | None = None,
) -> ExternalPointFeature:
    value = payload.get("feature")
    if not isinstance(value, dict):
        raise ProtocolError("feature must be an object")
    feature_id = _identifier(value.get("id"), "feature.id")
    kind = str(value.get("kind", ""))
    if kind not in FEATURE_KINDS:
        raise ProtocolError("feature.kind is unsupported")
    name = _text(value.get("name"), "feature.name", required=True)
    description = _text(value.get("description", ""), "feature.description")
    x, y, z = _position(value.get("position"))
    color_value = value.get("color")
    color: str | None = None
    if color_value is not None:
        color = str(color_value)
        if not _COLOR.fullmatch(color):
            raise ProtocolError("feature.color must be a six-digit hex color")
    expires_value = value.get("expires_at")
    expires_at = (
        parse_timestamp(expires_value, "feature.expires_at")
        if expires_value is not None
        else None
    )
    current = now or utc_now()
    if expires_at is not None and expires_at > current + timedelta(days=1):
        raise ProtocolError("feature expiry is unreasonably far in the future")
    return ExternalPointFeature(
        connection_id=connection_id,
        feature_id=feature_id,
        kind=kind,
        name=name,
        x=x,
        y=y,
        z=z,
        description=description,
        color=color,
        expires_at=expires_at,
    )


def parse_feature_remove(payload: dict[str, Any]) -> str:
    return _identifier(payload.get("feature_id"), "feature_id")


def _identifier(value: Any, field_name: str) -> str:
    text = str(value or "")
    if not _IDENTIFIER.fullmatch(text):
        raise ProtocolError(f"{field_name} is missing or invalid")
    return text


def _text(value: Any, field_name: str, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise ProtocolError(f"{field_name} must be text")
    text = value.strip()
    if (required and not text) or len(text) > MAX_TEXT_LENGTH:
        raise ProtocolError(f"{field_name} is missing or too long")
    return text


def _position(value: Any) -> tuple[float, float, float]:
    if not isinstance(value, dict):
        raise ProtocolError("position must be an object")
    try:
        x = float(value["x"])
        y = float(value["y"])
        z = float(value.get("z", 0.0))
    except (KeyError, TypeError, ValueError) as exc:
        raise ProtocolError("position coordinates must be numbers") from exc
    if not all(math.isfinite(item) and abs(item) <= 10_000_000 for item in (x, y, z)):
        raise ProtocolError("position is outside supported numeric limits")
    return x, y, z
