from datetime import timedelta

from core.overlay_store import ExternalPointFeature, OverlayStore
from integrations.protocol import utc_now


def test_overlay_store_is_scoped_and_prunes_expired_features():
    store = OverlayStore()
    now = utc_now()
    store.upsert(
        ExternalPointFeature(
            connection_id="one",
            feature_id="player:a",
            kind="player",
            name="A",
            x=1,
            y=2,
            expires_at=now - timedelta(seconds=1),
        )
    )
    store.upsert(
        ExternalPointFeature(
            connection_id="two",
            feature_id="marker:b",
            kind="marker",
            name="B",
            x=3,
            y=4,
        )
    )

    assert store.prune_expired(now) == 1
    assert [feature.name for feature in store.features] == ["B"]
    store.clear_connection("two")
    assert store.features == ()
