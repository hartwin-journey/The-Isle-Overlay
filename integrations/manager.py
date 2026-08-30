"""Permission-gated bridge between local state, transports, and remote overlays."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import logging
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from core.app_state import AppState
from core.models import Position, Waypoint
from core.overlay_store import OverlayStore
from integrations.adapters.base import IntegrationTransport
from integrations.adapters.websocket import WebSocketAdapter
from integrations.contracts import (
    CAPABILITY_POINTS_SUBSCRIBE,
    CAPABILITY_POSITION_PUBLISH,
    CAPABILITY_WAYPOINT_PUBLISH,
    IntegrationConfigurationError,
    MapIdentity,
    validate_room,
    validate_websocket_url,
)
from integrations.protocol import (
    ProtocolError,
    decode_message,
    encode_message,
    format_timestamp,
    parse_feature_remove,
    parse_remote_feature,
    parse_welcome_payload,
)

LOGGER = logging.getLogger(__name__)
TransportFactory = Callable[[str, str], IntegrationTransport]


class IntegrationManager(QObject):
    """Own one optional connection without granting it authority over local state."""

    status_changed = Signal(str)
    connection_changed = Signal(bool)

    def __init__(
        self,
        state: AppState,
        overlays: OverlayStore,
        map_identity: MapIdentity,
        *,
        transport_factory: TransportFactory | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.state = state
        self.overlays = overlays
        self.map_identity = map_identity
        self._transport_factory = transport_factory or (
            lambda url, token: WebSocketAdapter(url, token)
        )
        self._transport: IntegrationTransport | None = None
        self._connection_id = "primary"
        self._welcomed = False
        self._accepted_capabilities: frozenset[str] = frozenset()
        self._closing = False

        self._publish_timer = QTimer(self)
        self._publish_timer.timeout.connect(self._publish_current_position)
        self._expiry_timer = QTimer(self)
        self._expiry_timer.setInterval(1_000)
        self._expiry_timer.timeout.connect(self.overlays.prune_expired)
        self._expiry_timer.start()
        self._handshake_timer = QTimer(self)
        self._handshake_timer.setSingleShot(True)
        self._handshake_timer.setInterval(10_000)
        self._handshake_timer.timeout.connect(self._handshake_timed_out)
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.setInterval(3_000)
        self._reconnect_timer.timeout.connect(self.apply_settings)

        state.waypoint_changed.connect(self._on_waypoint_changed)

    @property
    def connected(self) -> bool:
        return self._transport is not None and self._welcomed

    @property
    def accepted_capabilities(self) -> frozenset[str]:
        return self._accepted_capabilities

    def apply_settings(self) -> None:
        """Reconnect from the currently shared settings dictionary."""

        self._reconnect_timer.stop()
        self.disconnect("External integrations: off")
        config = self._config
        if not bool(config.get("enabled", False)):
            return
        try:
            url = validate_websocket_url(str(config.get("websocket_url", "")))
            validate_room(str(config.get("room", "")))
        except IntegrationConfigurationError as exc:
            self._set_status(f"External integrations: {exc}")
            return
        try:
            transport = self._transport_factory(url, str(config.get("access_token", "")))
        except (IntegrationConfigurationError, RuntimeError, ValueError) as exc:
            self._set_status(f"External integrations: {exc}")
            return
        self._transport = transport
        transport.opened.connect(self._on_transport_opened)
        transport.closed.connect(self._on_transport_closed)
        transport.failed.connect(self._on_transport_failed)
        transport.text_received.connect(self._on_text_received)
        self._set_status("External integrations: connecting…")
        try:
            transport.open()
        except (OSError, RuntimeError, ValueError) as exc:
            self._set_status(f"External integrations: connection failed ({exc})")
            self.disconnect(emit_status=False)

    def disconnect(self, status: str = "External integrations: disconnected", *, emit_status: bool = True) -> None:
        transport = self._transport
        self._transport = None
        was_connected = self._welcomed
        self._welcomed = False
        self._accepted_capabilities = frozenset()
        self._publish_timer.stop()
        self._handshake_timer.stop()
        self._reconnect_timer.stop()
        self.overlays.clear_connection(self._connection_id)
        if transport is not None:
            self._detach_transport(transport)
            transport.close()
            transport.deleteLater()
        if was_connected:
            self.connection_changed.emit(False)
        if emit_status:
            self._set_status(status)

    def close(self) -> None:
        self._closing = True
        self.disconnect("External integrations: off")
        self._expiry_timer.stop()

    @property
    def _config(self) -> dict[str, Any]:
        value = self.state.settings.get("integration", {})
        return value if isinstance(value, dict) else {}

    def _detach_transport(self, transport: IntegrationTransport) -> None:
        for signal, callback in (
            (transport.opened, self._on_transport_opened),
            (transport.closed, self._on_transport_closed),
            (transport.failed, self._on_transport_failed),
            (transport.text_received, self._on_text_received),
        ):
            try:
                signal.disconnect(callback)
            except (RuntimeError, TypeError):
                pass

    @Slot()
    def _on_transport_opened(self) -> None:
        if self._transport is None:
            return
        requested = self._requested_capabilities()
        payload = {
            "client": {"name": "The Isle Companion", "version": "experimental-api-v1"},
            "display_name": self._display_name,
            "room": str(self._config.get("room", "default")),
            "capabilities": sorted(requested),
        }
        if not self._send("hello", payload):
            self._set_status("External integrations: could not send handshake")
            return
        self._handshake_timer.start()
        self._set_status("External integrations: authenticating…")

    @Slot(str)
    def _on_transport_closed(self, reason: str) -> None:
        if self._transport is None:
            return
        text = "External integrations: disconnected"
        if reason and not self._closing:
            text += f" ({reason})"
        self.disconnect(text)
        self._schedule_reconnect(text)

    @Slot(str)
    def _on_transport_failed(self, reason: str) -> None:
        if self._transport is not None:
            self._set_status(f"External integrations: connection error ({reason})")

    @Slot(str)
    def _on_text_received(self, raw: str) -> None:
        try:
            message = decode_message(raw, self.map_identity)
            if message.type == "welcome":
                self._accept_welcome(message.payload)
                return
            if not self._welcomed:
                raise ProtocolError("message received before welcome")
            if message.type == "feature.upsert":
                self._accept_feature(message.payload)
            elif message.type == "feature.remove":
                self._remove_feature(message.payload)
            elif message.type == "ping":
                self._send("pong", {"ping_id": message.message_id})
            elif message.type == "error":
                detail = str(message.payload.get("message", "remote service reported an error"))
                self._set_status(f"External integrations: {detail[:256]}")
        except (IntegrationConfigurationError, ProtocolError, ValueError) as exc:
            LOGGER.warning("Rejected external integration message: %s", exc)
            self._set_status(f"External integrations: rejected invalid message ({exc})")

    def _accept_welcome(self, payload: dict[str, Any]) -> None:
        if self._welcomed:
            raise ProtocolError("duplicate welcome message")
        _session_id, accepted = parse_welcome_payload(payload)
        requested = self._requested_capabilities()
        if not accepted.issubset(requested):
            raise ProtocolError("server granted capabilities that were not requested")
        self._accepted_capabilities = accepted
        self._welcomed = True
        self._handshake_timer.stop()
        interval = min(
            10_000,
            max(500, int(self._config.get("position_interval_ms", 1_000))),
        )
        self._publish_timer.setInterval(interval)
        if self._can_publish_position:
            self._publish_timer.start()
            self._publish_current_position()
        if self._can_publish_waypoint:
            self._publish_waypoint(self.state.active_waypoint)
        self.connection_changed.emit(True)
        service_name = str(self._config.get("service_name", "")).strip() or "service"
        self._set_status(f"External integrations: connected to {service_name}")

    def _accept_feature(self, payload: dict[str, Any]) -> None:
        if not self._can_receive_points:
            raise ProtocolError("remote point reception is not permitted")
        feature = parse_remote_feature(payload, self._connection_id)
        if feature.expires_at is not None and feature.expires_at <= datetime.now(timezone.utc):
            self.overlays.remove(self._connection_id, feature.feature_id)
            return
        self.overlays.upsert(feature)

    def _remove_feature(self, payload: dict[str, Any]) -> None:
        if not self._can_receive_points:
            raise ProtocolError("remote point reception is not permitted")
        self.overlays.remove(self._connection_id, parse_feature_remove(payload))

    def _requested_capabilities(self) -> frozenset[str]:
        config = self._config
        requested: set[str] = set()
        if bool(config.get("receive_points", False)):
            requested.add(CAPABILITY_POINTS_SUBSCRIBE)
        if bool(config.get("share_position", False)):
            requested.add(CAPABILITY_POSITION_PUBLISH)
        if bool(config.get("share_waypoint", False)):
            requested.add(CAPABILITY_WAYPOINT_PUBLISH)
        return frozenset(requested)

    @property
    def _display_name(self) -> str:
        return str(self._config.get("display_name", "")).strip() or "Player"

    @property
    def _can_receive_points(self) -> bool:
        return (
            bool(self._config.get("receive_points", False))
            and CAPABILITY_POINTS_SUBSCRIBE in self._accepted_capabilities
        )

    @property
    def _can_publish_position(self) -> bool:
        return (
            bool(self._config.get("share_position", False))
            and CAPABILITY_POSITION_PUBLISH in self._accepted_capabilities
        )

    @property
    def _can_publish_waypoint(self) -> bool:
        return (
            bool(self._config.get("share_waypoint", False))
            and CAPABILITY_WAYPOINT_PUBLISH in self._accepted_capabilities
        )

    @Slot()
    def _publish_current_position(self) -> None:
        position = self.state.current_position
        if not self._welcomed or not self._can_publish_position or position is None:
            return
        max_age = min(
            300,
            max(5, int(self._config.get("position_max_age_seconds", 30))),
        )
        observed_at = position.timestamp.astimezone(timezone.utc)
        if (datetime.now(timezone.utc) - observed_at).total_seconds() > max_age:
            return
        self._send(
            "position.update",
            {
                "position": {
                    "x": position.x,
                    "y": position.y,
                    "z": position.z,
                    "observed_at": format_timestamp(observed_at),
                }
            },
        )

    @Slot(object)
    def _on_waypoint_changed(self, waypoint: Waypoint | None) -> None:
        if self._welcomed and self._can_publish_waypoint:
            self._publish_waypoint(waypoint)

    def _publish_waypoint(self, waypoint: Waypoint | None) -> None:
        if waypoint is None:
            self._send("waypoint.clear", {"waypoint_id": "active"})
            return
        self._send(
            "waypoint.upsert",
            {
                "waypoint": {
                    "id": "active",
                    "name": waypoint.name[:256],
                    "position": {"x": waypoint.x, "y": waypoint.y, "z": waypoint.z},
                }
            },
        )

    def _send(self, message_type: str, payload: dict[str, Any]) -> bool:
        transport = self._transport
        if transport is None:
            return False
        try:
            encoded = encode_message(message_type, payload, self.map_identity)
        except ProtocolError as exc:
            LOGGER.error("Could not encode integration message: %s", exc)
            return False
        return transport.send_text(encoded)

    def _handshake_timed_out(self) -> None:
        text = "External integrations: handshake timed out"
        self.disconnect(text)
        self._schedule_reconnect(text)

    def _schedule_reconnect(self, status: str) -> None:
        if self._closing or not bool(self._config.get("enabled", False)):
            return
        self._reconnect_timer.start()
        self._set_status(f"{status}; retrying in 3 seconds")

    def _set_status(self, text: str) -> None:
        self.status_changed.emit(text)
