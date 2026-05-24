from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import (
    VenueInventorySnapshot,
    VenueMenuSnapshot,
    VenuePriceSnapshot,
    VenueSnapshot,
)
from app.models.enums import SyncEventStatus
from app.models.sync import MapSnapshotSyncEvent


@dataclass(frozen=True)
class MapSnapshotImportResult:
    event_id: str
    duplicate_event: bool
    venue_created: bool
    menus_created: int
    inventory_created: int
    prices_created: int


class MapSnapshotImportService:
    """Imports approved map/place snapshot payloads into recommendation read models."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def import_snapshot_event(self, payload: dict[str, Any]) -> MapSnapshotImportResult:
        event_id = _required_str(payload, "event_id")
        existing_event = self._session.scalar(
            select(MapSnapshotSyncEvent).where(
                MapSnapshotSyncEvent.event_id == event_id,
            ),
        )
        if (
            existing_event is not None
            and existing_event.status == SyncEventStatus.PROCESSED.value
        ):
            return MapSnapshotImportResult(
                event_id=event_id,
                duplicate_event=True,
                venue_created=False,
                menus_created=0,
                inventory_created=0,
                prices_created=0,
            )

        place_id = _required_str(payload, "place_id")
        place_revision = _required_str(payload, "place_revision")
        event = existing_event or MapSnapshotSyncEvent(
            event_id=event_id,
            event_type=_required_str(payload, "event_type"),
            place_id=place_id,
            place_revision=place_revision,
            menu_revision=_first_revision(payload.get("menus"), "menu_revision"),
            inventory_revision=_first_revision(
                payload.get("inventory"),
                "inventory_revision",
            ),
            price_revision=_first_revision(payload.get("prices"), "price_revision"),
            event_payload_json=payload,
            status=SyncEventStatus.PROCESSING.value,
            attempt_count=0,
        )
        self._session.add(event)

        venue, venue_created = self._upsert_venue_snapshot(
            payload=payload,
            place_id=place_id,
            place_revision=place_revision,
            event_id=event_id,
        )
        menus_created = sum(
            1
            for row in payload.get("menus", [])
            if self._upsert_menu_snapshot(venue, row)
        )
        inventory_created = sum(
            1
            for row in payload.get("inventory", [])
            if self._upsert_inventory_snapshot(venue, row)
        )
        prices_created = sum(
            1
            for row in payload.get("prices", [])
            if self._upsert_price_snapshot(venue, row)
        )

        event.status = SyncEventStatus.PROCESSED.value
        event.processed_at = datetime.now(UTC)
        event.last_error = None
        self._session.flush()
        return MapSnapshotImportResult(
            event_id=event_id,
            duplicate_event=False,
            venue_created=venue_created,
            menus_created=menus_created,
            inventory_created=inventory_created,
            prices_created=prices_created,
        )

    def _upsert_venue_snapshot(
        self,
        *,
        payload: dict[str, Any],
        place_id: str,
        place_revision: str,
        event_id: str,
    ) -> tuple[VenueSnapshot, bool]:
        existing = self._session.scalar(
            select(VenueSnapshot).where(
                VenueSnapshot.place_id == place_id,
                VenueSnapshot.place_revision == place_revision,
            ),
        )
        if existing is not None:
            return existing, False
        venue_payload = payload.get("venue") or {}
        snapshot_json = dict(venue_payload)
        if "lat" in payload and "lng" in payload:
            snapshot_json.setdefault("lat", payload["lat"])
            snapshot_json.setdefault("lng", payload["lng"])
        if "lat" in venue_payload and "lng" in venue_payload:
            snapshot_json.setdefault("lat", venue_payload["lat"])
            snapshot_json.setdefault("lng", venue_payload["lng"])
        venue = VenueSnapshot(
            place_id=place_id,
            place_revision=place_revision,
            name=_required_str(venue_payload, "name"),
            place_type=_required_str(venue_payload, "place_type"),
            address=venue_payload.get("address"),
            status=_required_str(venue_payload, "status"),
            publication_status=venue_payload.get("publication_status"),
            snapshot_json=snapshot_json,
            source_event_id=event_id,
            stale_after=_parse_datetime(venue_payload.get("stale_after")),
        )
        self._session.add(venue)
        self._session.flush()
        return venue, True

    def _upsert_menu_snapshot(
        self,
        venue: VenueSnapshot,
        payload: dict[str, Any],
    ) -> bool:
        menu_item_id = _required_str(payload, "menu_item_id")
        menu_revision = _required_str(payload, "menu_revision")
        existing = self._session.scalar(
            select(VenueMenuSnapshot).where(
                VenueMenuSnapshot.place_id == venue.place_id,
                VenueMenuSnapshot.menu_item_id == menu_item_id,
                VenueMenuSnapshot.menu_revision == menu_revision,
            ),
        )
        if existing is not None:
            return False
        self._session.add(
            VenueMenuSnapshot(
                venue_snapshot_id=venue.id,
                place_id=venue.place_id,
                menu_item_id=menu_item_id,
                menu_revision=menu_revision,
                beverage_item_id=_optional_uuid(payload.get("beverage_item_id")),
                menu_name=_required_str(payload, "menu_name"),
                menu_type=payload.get("menu_type"),
                status=_required_str(payload, "status"),
                snapshot_json=payload,
            ),
        )
        return True

    def _upsert_inventory_snapshot(
        self,
        venue: VenueSnapshot,
        payload: dict[str, Any],
    ) -> bool:
        inventory_revision = _required_str(payload, "inventory_revision")
        beverage_item_id = _optional_uuid(payload.get("beverage_item_id"))
        source_beverage_id = payload.get("source_beverage_id")
        existing = self._session.scalar(
            select(VenueInventorySnapshot).where(
                VenueInventorySnapshot.place_id == venue.place_id,
                VenueInventorySnapshot.beverage_item_id == beverage_item_id,
                VenueInventorySnapshot.source_beverage_id == source_beverage_id,
                VenueInventorySnapshot.inventory_revision == inventory_revision,
            ),
        )
        if existing is not None:
            return False
        self._session.add(
            VenueInventorySnapshot(
                venue_snapshot_id=venue.id,
                place_id=venue.place_id,
                beverage_item_id=beverage_item_id,
                source_beverage_id=source_beverage_id,
                inventory_revision=inventory_revision,
                availability_status=_required_str(payload, "availability_status"),
                confidence=payload.get("confidence"),
                last_seen_at=_parse_datetime(payload.get("last_seen_at")),
                expires_at=_parse_datetime(payload.get("expires_at")),
                snapshot_json=payload,
            ),
        )
        return True

    def _upsert_price_snapshot(
        self,
        venue: VenueSnapshot,
        payload: dict[str, Any],
    ) -> bool:
        price_revision = _required_str(payload, "price_revision")
        beverage_item_id = _optional_uuid(payload.get("beverage_item_id"))
        menu_item_id = payload.get("menu_item_id")
        existing = self._session.scalar(
            select(VenuePriceSnapshot).where(
                VenuePriceSnapshot.place_id == venue.place_id,
                VenuePriceSnapshot.beverage_item_id == beverage_item_id,
                VenuePriceSnapshot.menu_item_id == menu_item_id,
                VenuePriceSnapshot.price_revision == price_revision,
            ),
        )
        if existing is not None:
            return False
        self._session.add(
            VenuePriceSnapshot(
                venue_snapshot_id=venue.id,
                place_id=venue.place_id,
                beverage_item_id=beverage_item_id,
                menu_item_id=menu_item_id,
                price_revision=price_revision,
                price_krw=int(payload["price_krw"]),
                price_type=payload.get("price_type"),
                confidence=payload.get("confidence"),
                valid_from=_parse_datetime(payload.get("valid_from")),
                valid_until=_parse_datetime(payload.get("valid_until")),
                snapshot_json=payload,
            ),
        )
        return True


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} is required")
    return value


def _optional_uuid(value: Any) -> uuid.UUID | None:
    if value in (None, ""):
        return None
    return uuid.UUID(str(value))


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError("datetime fields must be ISO-8601 strings")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _first_revision(rows: Any, key: str) -> str | None:
    if not isinstance(rows, list) or not rows:
        return None
    value = rows[0].get(key)
    return value if isinstance(value, str) else None
