import copy
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QCoreApplication

from core.app_state import AppState
from core.models import Position, Waypoint
from core.overlay_store import OverlayStore
from core.settings import DEFAULT_SETTINGS
from integrations.adapters.base import IntegrationTransport
from integrations.contracts import DEFAULT_MAP_IDENTITY
from integrations.manager import IntegrationManager
from integrations.protocol import decode_message, encode_message, format_timestamp, utc_now


class FakeTransport(IntegrationTransport):
    def __init__(self) -> None:
        super().__init__()
        self.sent: list[str] = []
        self.was_closed = False

    def open(self) -> None:
        self.opened.emit()

    def close(self) -> None:
        self.was_closed = True

    def send_text(self, text: str) -> bool:
        self.sent.append(text)
        return True


def test_manager_gates_publication_and_keeps_remote_points_separate():
    app = QCoreApplication.instance() or QCoreApplication([])
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    settings["integration"].update(
        {
            "enabled": True,
            "service_name": "Test relay",
            "websocket_url": "ws://127.0.0.1:8765",
            "room": "test-pack",
            "display_name": "Local player",
            "receive_points": True,
            "share_position": True,
            "share_waypoint": True,
        }
    )
    state = AppState(settings)
    state.update_position(Position(100, 200, 3, datetime.now(timezone.utc)))
    overlays = OverlayStore()
    transport = FakeTransport()
    manager = IntegrationManager(
        state,
        overlays,
        DEFAULT_MAP_IDENTITY,
        transport_factory=lambda _url, _token: transport,
    )

    manager.apply_settings()
    hello = decode_message(transport.sent[0], DEFAULT_MAP_IDENTITY)
    assert hello.type == "hello"
    assert hello.payload["room"] == "test-pack"
    assert set(hello.payload["capabilities"]) == {
        "points.subscribe",
        "position.publish",
        "waypoint.publish",
    }

    transport.text_received.emit(
        encode_message(
            "welcome",
            {
                "session_id": "session-1",
                "capabilities": hello.payload["capabilities"],
            },
            DEFAULT_MAP_IDENTITY,
        )
    )
    app.processEvents()
    sent_types = [decode_message(item, DEFAULT_MAP_IDENTITY).type for item in transport.sent]
    assert "position.update" in sent_types
    assert "waypoint.clear" in sent_types

    state.set_waypoint(Waypoint("Meet", 500, 600, 7))
    assert decode_message(transport.sent[-1], DEFAULT_MAP_IDENTITY).type == "waypoint.upsert"

    expiry = utc_now() + timedelta(seconds=15)
    transport.text_received.emit(
        encode_message(
            "feature.upsert",
            {
                "feature": {
                    "id": "player:friend",
                    "kind": "player",
                    "name": "Friend",
                    "position": {"x": 700, "y": 800, "z": 9},
                    "expires_at": format_timestamp(expiry),
                }
            },
            DEFAULT_MAP_IDENTITY,
        )
    )
    app.processEvents()

    assert len(overlays.features) == 1
    assert overlays.features[0].name == "Friend"
    assert state.current_position is not None
    assert state.current_position.x == 100

    transport.text_received.emit(
        encode_message(
            "feature.remove",
            {"feature_id": "player:friend"},
            DEFAULT_MAP_IDENTITY,
        )
    )
    app.processEvents()
    assert overlays.features == ()

    manager.close()
    assert transport.was_closed
