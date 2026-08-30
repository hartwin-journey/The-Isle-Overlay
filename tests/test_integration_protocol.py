from dataclasses import replace
from datetime import timedelta
import json

import pytest

from integrations.contracts import (
    DEFAULT_MAP_IDENTITY,
    IntegrationConfigurationError,
    validate_websocket_url,
)
from integrations.protocol import (
    ProtocolError,
    decode_message,
    encode_message,
    format_timestamp,
    parse_remote_feature,
    utc_now,
)


def test_protocol_round_trip_preserves_validated_envelope():
    encoded = encode_message("ping", {"value": 1}, DEFAULT_MAP_IDENTITY)
    decoded = decode_message(encoded, DEFAULT_MAP_IDENTITY)

    assert decoded.type == "ping"
    assert decoded.payload == {"value": 1}
    assert decoded.sent_at.tzinfo is not None


def test_protocol_rejects_map_version_mismatch():
    other_map = replace(DEFAULT_MAP_IDENTITY, map_version="different")
    encoded = encode_message("ping", {}, other_map)

    with pytest.raises(ProtocolError, match="map version"):
        decode_message(encoded, DEFAULT_MAP_IDENTITY)


def test_protocol_rejects_oversized_and_unknown_messages():
    encoded = encode_message("ping", {}, DEFAULT_MAP_IDENTITY)
    value = json.loads(encoded)
    value["type"] = "execute.command"

    with pytest.raises(ProtocolError, match="unsupported message type"):
        decode_message(json.dumps(value), DEFAULT_MAP_IDENTITY)
    with pytest.raises(ProtocolError, match="64 KiB"):
        decode_message("x" * 70_000, DEFAULT_MAP_IDENTITY)


def test_remote_feature_is_typed_and_bounded():
    now = utc_now()
    feature = parse_remote_feature(
        {
            "feature": {
                "id": "player:friend-1",
                "kind": "player",
                "name": "Friend",
                "position": {"x": 1000, "y": 2000, "z": 30},
                "color": "#A78BFA",
                "expires_at": format_timestamp(now + timedelta(seconds=15)),
            }
        },
        "test-connection",
        now=now,
    )

    assert feature.connection_id == "test-connection"
    assert feature.feature_id == "player:friend-1"
    assert feature.x == 1000
    assert feature.expires_at is not None


@pytest.mark.parametrize(
    "url",
    [
        "ws://example.com:8765",
        "http://example.com",
        "wss://user:password@example.com",
    ],
)
def test_remote_connection_url_must_be_secure(url):
    with pytest.raises(IntegrationConfigurationError):
        validate_websocket_url(url)


def test_loopback_and_secure_websocket_urls_are_allowed():
    assert validate_websocket_url("ws://127.0.0.1:8765") == "ws://127.0.0.1:8765"
    assert validate_websocket_url("wss://example.com/companion") == "wss://example.com/companion"
