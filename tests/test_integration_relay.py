import copy
from datetime import datetime, timezone

from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest

from core.app_state import AppState
from core.models import Position
from core.overlay_store import OverlayStore
from core.settings import DEFAULT_SETTINGS
from integrations.contracts import DEFAULT_MAP_IDENTITY
from integrations.manager import IntegrationManager
from tools.integration_relay import IntegrationRelay


def _settings(name: str, url: str, *, receive: bool, share: bool) -> dict:
    values = copy.deepcopy(DEFAULT_SETTINGS)
    values["integration"].update(
        {
            "enabled": True,
            "service_name": "Test relay",
            "websocket_url": url,
            "room": "relay-test",
            "display_name": name,
            "access_token": "test-token",
            "receive_points": receive,
            "share_position": share,
        }
    )
    return values


def test_reference_relay_broadcasts_between_real_websocket_clients():
    app = QCoreApplication.instance() or QCoreApplication([])
    relay = IntegrationRelay("127.0.0.1", 0, "test-token", DEFAULT_MAP_IDENTITY)

    receiver_state = AppState(_settings("Receiver", relay.address, receive=True, share=False))
    receiver_overlays = OverlayStore()
    receiver = IntegrationManager(
        receiver_state,
        receiver_overlays,
        DEFAULT_MAP_IDENTITY,
    )
    receiver.apply_settings()
    QTest.qWait(100)
    assert receiver.connected

    sender_state = AppState(_settings("Sender", relay.address, receive=False, share=True))
    sender_state.update_position(Position(1234, 5678, 90, datetime.now(timezone.utc)))
    sender = IntegrationManager(
        sender_state,
        OverlayStore(),
        DEFAULT_MAP_IDENTITY,
    )
    sender.apply_settings()

    for _attempt in range(20):
        if receiver_overlays.features:
            break
        QTest.qWait(50)
    app.processEvents()

    assert sender.connected
    assert len(receiver_overlays.features) == 1
    feature = receiver_overlays.features[0]
    assert feature.name == "Sender"
    assert (feature.x, feature.y, feature.z) == (1234, 5678, 90)

    sender.close()
    receiver.close()
    relay.close()
    app.processEvents()
