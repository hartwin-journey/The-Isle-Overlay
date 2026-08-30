"""Small reference room relay for The Isle Companion integration protocol.

This is intentionally a reference implementation, not a hosted service. Remote
deployments should put it behind an HTTPS reverse proxy so clients use wss://.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import timedelta
import os
from pathlib import Path
import secrets
import sys
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QHostAddress
from PySide6.QtWebSockets import QWebSocket, QWebSocketProtocol, QWebSocketServer

from integrations.contracts import (
    CAPABILITY_POINTS_SUBSCRIBE,
    CAPABILITY_POSITION_PUBLISH,
    CAPABILITY_WAYPOINT_PUBLISH,
    KNOWN_CAPABILITIES,
    MapIdentity,
    load_map_identity,
)
from integrations.protocol import (
    ProtocolError,
    decode_message,
    encode_message,
    format_timestamp,
    parse_hello_payload,
    parse_position_payload,
    parse_waypoint_payload,
    utc_now,
)


@dataclass(slots=True)
class Peer:
    socket: QWebSocket
    session_id: str = field(default_factory=lambda: str(uuid4()))
    room: str = ""
    display_name: str = "Player"
    capabilities: frozenset[str] = frozenset()
    welcomed: bool = False


class IntegrationRelay:
    def __init__(
        self,
        host: str,
        port: int,
        access_token: str,
        map_identity: MapIdentity,
    ) -> None:
        self.access_token = access_token
        self.map_identity = map_identity
        self.peers: dict[int, Peer] = {}
        self.server = QWebSocketServer(
            "The Isle Companion reference relay",
            QWebSocketServer.SslMode.NonSecureMode,
        )
        self.server.newConnection.connect(self._accept_connection)
        if not self.server.listen(QHostAddress(host), port):
            raise RuntimeError(self.server.errorString())

    @property
    def address(self) -> str:
        return f"ws://{self.server.serverAddress().toString()}:{self.server.serverPort()}"

    def close(self) -> None:
        for peer in list(self.peers.values()):
            peer.socket.close(
                QWebSocketProtocol.CloseCode.CloseCodeGoingAway,
                "Relay shutting down",
            )
        self.server.close()

    def _accept_connection(self) -> None:
        socket = self.server.nextPendingConnection()
        if socket is None:
            return
        if self.access_token:
            header = bytes(socket.request().rawHeader("Authorization")).decode(
                "utf-8", errors="replace"
            )
            expected = f"Bearer {self.access_token}"
            if not secrets.compare_digest(header, expected):
                socket.close(
                    QWebSocketProtocol.CloseCode.CloseCodePolicyViolated,
                    "Invalid access token",
                )
                socket.deleteLater()
                return
        peer = Peer(socket=socket)
        peer_key = id(socket)
        self.peers[peer_key] = peer
        socket.textMessageReceived.connect(
            lambda raw, key=peer_key: self._receive_text(key, raw)
        )
        socket.disconnected.connect(lambda key=peer_key: self._remove_peer(key))

    def _receive_text(self, peer_key: int, raw: str) -> None:
        peer = self.peers.get(peer_key)
        if peer is None:
            return
        try:
            message = decode_message(raw, self.map_identity)
            if not peer.welcomed:
                if message.type != "hello":
                    raise ProtocolError("hello must be the first message")
                self._welcome(peer, message.payload)
                return
            if message.type == "position.update":
                self._publish_position(peer, message.payload)
            elif message.type == "waypoint.upsert":
                self._publish_waypoint(peer, message.payload)
            elif message.type == "waypoint.clear":
                self._broadcast_remove(peer, f"waypoint:{peer.session_id}")
            elif message.type == "ping":
                self._send(peer, "pong", {"ping_id": message.message_id})
            else:
                raise ProtocolError(f"clients may not send {message.type}")
        except (ProtocolError, ValueError) as exc:
            self._send(peer, "error", {"code": "invalid_message", "message": str(exc)[:256]})

    def _welcome(self, peer: Peer, payload: dict[str, Any]) -> None:
        room, display_name, requested = parse_hello_payload(payload)
        peer.room = room
        peer.display_name = display_name
        peer.capabilities = requested.intersection(KNOWN_CAPABILITIES)
        peer.welcomed = True
        self._send(
            peer,
            "welcome",
            {
                "session_id": peer.session_id,
                "capabilities": sorted(peer.capabilities),
            },
        )
        print(f"Connected {peer.display_name!r} to room {peer.room!r}", flush=True)

    def _publish_position(self, peer: Peer, payload: dict[str, Any]) -> None:
        self._require(peer, CAPABILITY_POSITION_PUBLISH)
        x, y, z, observed_at = parse_position_payload(payload)
        expires_at = utc_now() + timedelta(seconds=15)
        self._broadcast_feature(
            peer,
            {
                "id": f"player:{peer.session_id}",
                "kind": "player",
                "name": peer.display_name,
                "description": f"Shared position observed {format_timestamp(observed_at)}",
                "position": {"x": x, "y": y, "z": z},
                "expires_at": format_timestamp(expires_at),
            },
        )

    def _publish_waypoint(self, peer: Peer, payload: dict[str, Any]) -> None:
        self._require(peer, CAPABILITY_WAYPOINT_PUBLISH)
        name, x, y, z = parse_waypoint_payload(payload)
        self._broadcast_feature(
            peer,
            {
                "id": f"waypoint:{peer.session_id}",
                "kind": "waypoint",
                "name": f"{peer.display_name}: {name}"[:256],
                "description": "Shared active waypoint",
                "position": {"x": x, "y": y, "z": z},
            },
        )

    @staticmethod
    def _require(peer: Peer, capability: str) -> None:
        if capability not in peer.capabilities:
            raise ProtocolError(f"capability not granted: {capability}")

    def _broadcast_feature(self, source: Peer, feature: dict[str, Any]) -> None:
        self._broadcast(source, "feature.upsert", {"feature": feature})

    def _broadcast_remove(self, source: Peer, feature_id: str) -> None:
        self._broadcast(source, "feature.remove", {"feature_id": feature_id})

    def _broadcast(self, source: Peer, message_type: str, payload: dict[str, Any]) -> None:
        for target in self.peers.values():
            if (
                target is source
                or not target.welcomed
                or target.room != source.room
                or CAPABILITY_POINTS_SUBSCRIBE not in target.capabilities
            ):
                continue
            self._send(target, message_type, payload)

    def _send(self, peer: Peer, message_type: str, payload: dict[str, Any]) -> None:
        try:
            peer.socket.sendTextMessage(
                encode_message(message_type, payload, self.map_identity)
            )
        except ProtocolError:
            peer.socket.close(
                QWebSocketProtocol.CloseCode.CloseCodeProtocolError,
                "Relay could not encode message",
            )

    def _remove_peer(self, peer_key: int) -> None:
        peer = self.peers.pop(peer_key, None)
        if peer is None:
            return
        if peer.welcomed:
            self._broadcast_remove(peer, f"player:{peer.session_id}")
            self._broadcast_remove(peer, f"waypoint:{peer.session_id}")
            print(f"Disconnected {peer.display_name!r} from room {peer.room!r}", flush=True)
        try:
            peer.socket.deleteLater()
        except RuntimeError:
            pass


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the reference companion WebSocket relay")
    parser.add_argument("--host", default="127.0.0.1", help="listen address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="listen port (default: 8765)")
    parser.add_argument(
        "--token",
        default=os.environ.get("TIC_RELAY_TOKEN", ""),
        help="bearer token; TIC_RELAY_TOKEN is preferred so it is not visible in the process list",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    if not 1 <= arguments.port <= 65_535:
        print("Port must be between 1 and 65535", file=sys.stderr)
        return 2
    app = QCoreApplication([sys.argv[0]])
    identity = load_map_identity(PROJECT_ROOT / "map" / "manifest.json")
    try:
        relay = IntegrationRelay(arguments.host, arguments.port, arguments.token, identity)
    except RuntimeError as exc:
        print(f"Could not start relay: {exc}", file=sys.stderr)
        return 1
    print(
        f"Reference relay listening on {relay.address} for {identity.display_name} "
        f"{identity.map_version}",
        flush=True,
    )
    if not arguments.token:
        print("Warning: no access token is configured", flush=True)
    app.aboutToQuit.connect(relay.close)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
