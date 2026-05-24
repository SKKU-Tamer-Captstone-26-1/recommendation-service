from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.models.sync import MapSnapshotSyncCursor
from app.services.map_snapshot_import import MapSnapshotImportResult
from app.services.map_snapshot_sync import (
    MapSnapshotEventPage,
    MapSnapshotSyncService,
    parse_map_snapshot_event_page,
)


def test_parse_map_snapshot_event_page_validates_v1_contract() -> None:
    page = parse_map_snapshot_event_page(
        {
            "cursor": "cur_1",
            "next_cursor": "cur_2",
            "has_more": True,
            "snapshot_watermark": "2026-05-23T00:00:00Z",
            "events": [
                {
                    "contract_version": "map_snapshot_event_v1",
                    "event_id": "map_evt_1",
                    "event_type": "inventory.updated",
                    "occurred_at": "2026-05-23T00:00:00Z",
                    "place_id": "place_1",
                    "place_revision": "place_rev_1",
                    "venue": {
                        "name": "Bottle Shop",
                        "place_type": "bottle_shop",
                        "status": "active",
                        "publication_status": "published",
                        "lat": 37.5,
                        "lng": 127.0,
                    },
                    "menus": [
                        {
                            "menu_item_id": "menu_1",
                            "menu_revision": "menu_rev_1",
                            "menu_name": "Test Bourbon",
                            "status": "active",
                        },
                    ],
                    "inventory": [
                        {
                            "inventory_revision": "inv_rev_1",
                            "availability_status": "available",
                            "confidence": 0.9,
                        },
                    ],
                    "prices": [
                        {
                            "price_revision": "price_rev_1",
                            "price_krw": 42000,
                            "confidence": 0.85,
                        },
                    ],
                },
            ],
        },
    )

    assert page.next_cursor == "cur_2"
    assert page.has_more
    assert page.snapshot_watermark == "2026-05-23T00:00:00Z"
    assert page.events[0]["event_id"] == "map_evt_1"


def test_parse_map_snapshot_event_page_rejects_missing_confidence() -> None:
    with pytest.raises(ValueError, match="confidence"):
        parse_map_snapshot_event_page(
            {
                "next_cursor": None,
                "has_more": False,
                "snapshot_watermark": "2026-05-23T00:00:00Z",
                "events": [
                    {
                        "contract_version": "map_snapshot_event_v1",
                        "event_id": "map_evt_1",
                        "event_type": "inventory.updated",
                        "occurred_at": "2026-05-23T00:00:00Z",
                        "place_id": "place_1",
                        "place_revision": "place_rev_1",
                        "venue": {
                            "name": "Bottle Shop",
                            "place_type": "bottle_shop",
                            "status": "active",
                            "publication_status": "published",
                            "lat": 37.5,
                            "lng": 127.0,
                        },
                        "inventory": [
                            {
                                "inventory_revision": "inv_rev_1",
                                "availability_status": "available",
                            },
                        ],
                    },
                ],
            },
        )


def test_map_snapshot_sync_advances_cursor_after_importing_page() -> None:
    cursor = MapSnapshotSyncCursor(
        source_name="map-service",
        cursor_value="cur_1",
        metadata_json={},
    )
    session = MagicMock(spec=Session)
    session.scalar.return_value = cursor
    client = _FakeClient(
        MapSnapshotEventPage(
            cursor="cur_1",
            next_cursor="cur_2",
            has_more=False,
            snapshot_watermark="2026-05-23T00:00:00Z",
            events=({"event_id": "map_evt_1"},),
        ),
    )
    importer = _FakeImporter(
        MapSnapshotImportResult(
            event_id="map_evt_1",
            duplicate_event=False,
            venue_created=True,
            menus_created=1,
            inventory_created=1,
            prices_created=1,
        ),
    )

    result = MapSnapshotSyncService(session, client, importer).sync_once(
        source_name="map-service",
        limit=25,
    )

    assert client.calls == [("cur_1", 25)]
    assert importer.events == [{"event_id": "map_evt_1"}]
    assert cursor.cursor_value == "cur_2"
    assert cursor.metadata_json["last_snapshot_watermark"] == "2026-05-23T00:00:00Z"
    assert result.events_processed == 1
    assert result.venues_created == 1
    session.flush.assert_called()


class _FakeClient:
    def __init__(self, page: MapSnapshotEventPage) -> None:
        self._page = page
        self.calls: list[tuple[str | None, int]] = []

    def list_snapshot_events(
        self,
        *,
        cursor: str | None,
        limit: int,
    ) -> MapSnapshotEventPage:
        self.calls.append((cursor, limit))
        return self._page


class _FakeImporter:
    def __init__(self, result: MapSnapshotImportResult) -> None:
        self._result = result
        self.events: list[dict[str, object]] = []

    def import_snapshot_event(
        self,
        payload: dict[str, object],
    ) -> MapSnapshotImportResult:
        self.events.append(payload)
        return self._result
