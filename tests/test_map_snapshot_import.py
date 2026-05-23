from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.models.enums import SyncEventStatus
from app.models.sync import MapSnapshotSyncEvent
from app.services.map_snapshot_import import MapSnapshotImportService


def test_map_snapshot_import_skips_processed_duplicate_event() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = MapSnapshotSyncEvent(
        event_id="map_evt_1",
        event_type="inventory.updated",
        place_id="place_1",
        status=SyncEventStatus.PROCESSED.value,
        event_payload_json={},
    )

    result = MapSnapshotImportService(session).import_snapshot_event(
        {
            "event_id": "map_evt_1",
            "event_type": "inventory.updated",
            "place_id": "place_1",
            "place_revision": "place_rev_1",
        },
    )

    assert result.duplicate_event
    session.add.assert_not_called()


def test_map_snapshot_import_creates_read_model_rows_from_payload() -> None:
    session = MagicMock(spec=Session)
    session.scalar.side_effect = [None, None, None, None, None]
    beverage_id = "11111111-1111-4111-8111-111111111111"
    now = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)

    result = MapSnapshotImportService(session).import_snapshot_event(
        {
            "event_id": "map_evt_2",
            "event_type": "price.updated",
            "place_id": "place_2",
            "place_revision": "place_rev_2",
            "lat": 37.5,
            "lng": 127.0,
            "venue": {
                "name": "Bottle Shop",
                "place_type": "bottle_shop",
                "address": "Seoul",
                "status": "active",
                "publication_status": "published",
            },
            "menus": [
                {
                    "menu_item_id": "menu_2",
                    "menu_revision": "menu_rev_2",
                    "beverage_item_id": beverage_id,
                    "menu_name": "Test Bottle",
                    "status": "active",
                },
            ],
            "inventory": [
                {
                    "inventory_revision": "inv_rev_2",
                    "beverage_item_id": beverage_id,
                    "availability_status": "available",
                    "confidence": 0.9,
                    "last_seen_at": now.isoformat(),
                },
            ],
            "prices": [
                {
                    "price_revision": "price_rev_2",
                    "beverage_item_id": beverage_id,
                    "menu_item_id": "menu_2",
                    "price_krw": 42000,
                    "confidence": 0.85,
                    "valid_until": (now + timedelta(days=2)).isoformat(),
                },
            ],
        },
    )

    assert not result.duplicate_event
    assert result.venue_created
    assert result.menus_created == 1
    assert result.inventory_created == 1
    assert result.prices_created == 1
    assert session.add.call_count == 5
