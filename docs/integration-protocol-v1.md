# The Isle Companion integration protocol v1

This document defines the experimental, server-agnostic JSON protocol used by optional external
connections. It does not expose the local clipboard, OCR engine, map renderer, settings, files,
or game process.

## Transport

- UTF-8 JSON text messages over WebSocket.
- Remote endpoints must use `wss://`.
- The client allows unencrypted `ws://` only on loopback for development.
- Maximum encoded message size: 65,536 bytes.
- Authentication is transport-specific. The built-in adapter sends an optional bearer token in
  the WebSocket HTTP `Authorization` header.

## Envelope

Every message has the same envelope:

```json
{
  "protocol": "tic",
  "version": 1,
  "type": "ping",
  "message_id": "f25297ee-3605-4535-a142-d13ba27facb7",
  "sent_at": "2026-08-30T12:00:00.000Z",
  "map": {
    "game": "the-isle-evrima",
    "id": "gateway",
    "version": "0.21.772",
    "coordinate_space": "the-isle-world-v1",
    "units": "game-world-units"
  },
  "payload": {}
}
```

Protocol name, version, map identity, map version, coordinate space, and units must match exactly.
Coordinates are game-world X/Y/Z values. Pixel or raster coordinates are never exchanged.

Identifiers are 1–128 ASCII letters, numbers, dots, underscores, colons, or hyphens. Human text
fields are limited to 256 characters. Timestamps are timezone-aware RFC 3339 values.

## Capability handshake

The client sends `hello` first:

```json
{
  "type": "hello",
  "payload": {
    "client": {
      "name": "The Isle Companion",
      "version": "experimental-api-v1"
    },
    "display_name": "Felix",
    "room": "gateway-group",
    "capabilities": [
      "points.subscribe",
      "position.publish",
      "waypoint.publish"
    ]
  }
}
```

The example omits the unchanged envelope fields. The server replies within ten seconds:

```json
{
  "type": "welcome",
  "payload": {
    "session_id": "9dd31c68-f015-4624-b2e1-d7109184bf50",
    "capabilities": [
      "points.subscribe",
      "position.publish",
      "waypoint.publish"
    ]
  }
}
```

The server may grant a subset of the requested capabilities. It must never grant an unrequested
capability. No application message is accepted before `welcome`.

Capabilities:

| Capability | Direction | Meaning |
| --- | --- | --- |
| `points.subscribe` | Server → client | Receive validated player, waypoint, and marker points. |
| `position.publish` | Client → server | Publish the user's precise current position. |
| `waypoint.publish` | Client → server | Publish the user's active waypoint or clear it. |

## Publish current position

```json
{
  "type": "position.update",
  "payload": {
    "position": {
      "x": -173000.0,
      "y": -62000.0,
      "z": 21112.882,
      "observed_at": "2026-08-30T11:59:59.500Z"
    }
  }
}
```

The built-in client publishes at most once per configured interval and periodically refreshes a
recently observed value while connected. It stops refreshing stale local positions so a server's
short feature expiry can remove them. Servers should rate-limit independently.

## Publish or clear an active waypoint

```json
{
  "type": "waypoint.upsert",
  "payload": {
    "waypoint": {
      "id": "active",
      "name": "Meet here",
      "position": {
        "x": 10000.0,
        "y": 12000.0,
        "z": 0.0
      }
    }
  }
}
```

```json
{
  "type": "waypoint.clear",
  "payload": {
    "waypoint_id": "active"
  }
}
```

## Receive or remove a point feature

```json
{
  "type": "feature.upsert",
  "payload": {
    "feature": {
      "id": "player:9dd31c68-f015-4624-b2e1-d7109184bf50",
      "kind": "player",
      "name": "Felix",
      "description": "Shared group position",
      "position": {
        "x": -173000.0,
        "y": -62000.0,
        "z": 21112.882
      },
      "color": "#A78BFA",
      "expires_at": "2026-08-30T12:00:15.000Z"
    }
  }
}
```

Allowed v1 kinds are `player`, `waypoint`, and `marker`. `color` is optional and, when present,
must be `#RRGGBB`. `expires_at` is optional but strongly recommended for live player points and
may not be more than 24 hours in the future.

```json
{
  "type": "feature.remove",
  "payload": {
    "feature_id": "player:9dd31c68-f015-4624-b2e1-d7109184bf50"
  }
}
```

Features are scoped to the connection, live only in memory, and are cleared when it disconnects.
An incoming player feature never updates the client's authoritative local player position. An
incoming waypoint never silently replaces the active local waypoint.

## Keepalive and errors

Either side may send `ping`; the receiver answers `pong` with the original message ID:

```json
{
  "type": "pong",
  "payload": {
    "ping_id": "f25297ee-3605-4535-a142-d13ba27facb7"
  }
}
```

Recoverable protocol errors use:

```json
{
  "type": "error",
  "payload": {
    "code": "invalid_message",
    "message": "position coordinates must be numbers"
  }
}
```

A service may close the socket for authentication failure, repeated invalid messages, rate-limit
abuse, or unsupported protocol/map versions.

## Server safety requirements

- Authorize users per room and capability.
- Construct fresh outbound messages from validated fields; do not forward raw client JSON.
- Bound message rate, room membership, text sizes, and retained state.
- Give player positions short expiries and remove session features on disconnect.
- Do not log bearer tokens or precise coordinates unless the service explicitly documents that
  retention and obtains appropriate consent.
- Treat display names, descriptions, and colors as untrusted data even though the desktop client
  applies its own validation.
