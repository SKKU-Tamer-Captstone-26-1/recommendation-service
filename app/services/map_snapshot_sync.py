from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.sync import MapSnapshotSyncCursor
from app.services.map_snapshot_import import (
    MapSnapshotImportResult,
    MapSnapshotImportService,
)

MAP_SNAPSHOT_CONTRACT_VERSION = "map_snapshot_event_v1"
SUPPORTED_MAP_SNAPSHOT_EVENT_TYPES = frozenset(
    {
        "place.published",
        "place.updated",
        "place.hidden",
        "place.closed",
        "place.merged",
        "place.deleted",
        "menu.updated",
        "inventory.updated",
        "price.updated",
    },
)


@dataclass(frozen=True)
class MapSnapshotEventPage:
    cursor: str | None
    next_cursor: str | None
    has_more: bool
    snapshot_watermark: str
    events: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class MapSnapshotSyncResult:
    source_name: str
    previous_cursor: str | None
    next_cursor: str | None
    has_more: bool
    snapshot_watermark: str
    events_received: int
    events_processed: int
    duplicate_events: int
    venues_created: int
    menus_created: int
    inventory_created: int
    prices_created: int


class MapSnapshotClient(Protocol):
    def list_snapshot_events(
        self,
        *,
        cursor: str | None,
        limit: int,
    ) -> MapSnapshotEventPage:
        """Return one page of map-service snapshot events."""


class MapSnapshotImporter(Protocol):
    def import_snapshot_event(self, payload: dict[str, Any]) -> MapSnapshotImportResult:
        """Import one already-approved snapshot event payload."""


class HttpMapSnapshotClient:
    """HTTP client for the map-service recommendation snapshot feed."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client or httpx.Client(
            base_url=self._settings.map_service_url,
            timeout=self._settings.map_snapshot_request_timeout_seconds,
        )

    def list_snapshot_events(
        self,
        *,
        cursor: str | None,
        limit: int,
    ) -> MapSnapshotEventPage:
        params: dict[str, str | int] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        response = self._client.get(
            self._settings.map_snapshot_events_path,
            params=params,
        )
        response.raise_for_status()
        return parse_map_snapshot_event_page(response.json())


class MapSnapshotSyncService:
    """Pulls map-service snapshot events and imports them into read models."""

    def __init__(
        self,
        session: Session,
        client: MapSnapshotClient,
        importer: MapSnapshotImporter | None = None,
    ) -> None:
        self._session = session
        self._client = client
        self._importer = importer or MapSnapshotImportService(session)

    def sync_once(
        self,
        *,
        source_name: str = "map-service",
        limit: int | None = None,
    ) -> MapSnapshotSyncResult:
        settings = get_settings()
        resolved_limit = limit or settings.map_snapshot_events_page_size
        if resolved_limit <= 0:
            raise ValueError("limit must be greater than zero")

        cursor = self._get_or_create_cursor(source_name)
        previous_cursor = cursor.cursor_value
        page = self._client.list_snapshot_events(
            cursor=previous_cursor,
            limit=resolved_limit,
        )

        processed = 0
        duplicate_events = 0
        venues_created = 0
        menus_created = 0
        inventory_created = 0
        prices_created = 0
        for event in page.events:
            result = self._importer.import_snapshot_event(event)
            processed += 1
            duplicate_events += 1 if result.duplicate_event else 0
            venues_created += 1 if result.venue_created else 0
            menus_created += result.menus_created
            inventory_created += result.inventory_created
            prices_created += result.prices_created

        cursor.cursor_value = page.next_cursor
        cursor.last_synced_at = datetime.now(UTC)
        cursor.metadata_json = {
            **(cursor.metadata_json or {}),
            "last_page_cursor": page.cursor,
            "last_snapshot_watermark": page.snapshot_watermark,
            "last_events_received": len(page.events),
            "last_events_processed": processed,
            "has_more": page.has_more,
        }
        self._session.add(cursor)
        self._session.flush()

        return MapSnapshotSyncResult(
            source_name=source_name,
            previous_cursor=previous_cursor,
            next_cursor=page.next_cursor,
            has_more=page.has_more,
            snapshot_watermark=page.snapshot_watermark,
            events_received=len(page.events),
            events_processed=processed,
            duplicate_events=duplicate_events,
            venues_created=venues_created,
            menus_created=menus_created,
            inventory_created=inventory_created,
            prices_created=prices_created,
        )

    def _get_or_create_cursor(self, source_name: str) -> MapSnapshotSyncCursor:
        cursor = self._session.scalar(
            select(MapSnapshotSyncCursor).where(
                MapSnapshotSyncCursor.source_name == source_name,
            ),
        )
        if cursor is not None:
            return cursor
        cursor = MapSnapshotSyncCursor(
            source_name=source_name,
            cursor_value=None,
            metadata_json={},
        )
        self._session.add(cursor)
        self._session.flush()
        return cursor


def parse_map_snapshot_event_page(payload: Any) -> MapSnapshotEventPage:
    if not isinstance(payload, dict):
        raise ValueError("map snapshot page must be an object")
    events = payload.get("events")
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    has_more = payload.get("has_more")
    if not isinstance(has_more, bool):
        raise ValueError("has_more must be a boolean")
    cursor = _optional_str(payload, "cursor")
    next_cursor = _optional_str(payload, "next_cursor")
    if has_more and next_cursor is None:
        raise ValueError("next_cursor is required when has_more is true")
    snapshot_watermark = _required_str(payload, "snapshot_watermark")

    parsed_events: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError(f"events[{index}] must be an object")
        _validate_map_snapshot_event(event, index)
        parsed_events.append(event)

    return MapSnapshotEventPage(
        cursor=cursor,
        next_cursor=next_cursor,
        has_more=has_more,
        snapshot_watermark=snapshot_watermark,
        events=tuple(parsed_events),
    )


def _validate_map_snapshot_event(event: dict[str, Any], index: int) -> None:
    prefix = f"events[{index}]"
    contract_version = _required_str(event, "contract_version")
    if contract_version != MAP_SNAPSHOT_CONTRACT_VERSION:
        raise ValueError(
            f"{prefix}.contract_version must be {MAP_SNAPSHOT_CONTRACT_VERSION}",
        )
    event_type = _required_str(event, "event_type")
    if event_type not in SUPPORTED_MAP_SNAPSHOT_EVENT_TYPES:
        raise ValueError(f"{prefix}.event_type is unsupported: {event_type}")
    for key in ("event_id", "occurred_at", "place_id", "place_revision"):
        _required_str(event, key)

    venue = event.get("venue")
    if not isinstance(venue, dict):
        raise ValueError(f"{prefix}.venue must be an object")
    for key in ("name", "place_type", "status", "publication_status"):
        _required_str(venue, key)
    _required_coordinate(venue, "lat", prefix)
    _required_coordinate(venue, "lng", prefix)

    _validate_rows(
        event.get("menus", []),
        "menus",
        ("menu_item_id", "menu_revision", "menu_name", "status"),
        prefix,
    )
    _validate_rows(
        event.get("inventory", []),
        "inventory",
        ("inventory_revision", "availability_status"),
        prefix,
        require_confidence=True,
    )
    _validate_rows(
        event.get("prices", []),
        "prices",
        ("price_revision", "price_krw"),
        prefix,
        require_confidence=True,
    )


def _validate_rows(
    rows: Any,
    name: str,
    required_fields: tuple[str, ...],
    prefix: str,
    *,
    require_confidence: bool = False,
) -> None:
    if not isinstance(rows, list):
        raise ValueError(f"{prefix}.{name} must be a list")
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"{prefix}.{name}[{row_index}] must be an object")
        for field in required_fields:
            if field == "price_krw":
                if not isinstance(row.get(field), int):
                    raise ValueError(
                        f"{prefix}.{name}[{row_index}].{field} is required",
                    )
            else:
                _required_str(row, field)
        if require_confidence:
            confidence = row.get("confidence")
            if not isinstance(confidence, int | float) or not 0.0 <= confidence <= 1.0:
                raise ValueError(
                    f"{prefix}.{name}[{row_index}].confidence must be 0.0..1.0",
                )


def _required_coordinate(payload: dict[str, Any], key: str, prefix: str) -> None:
    value = payload.get(key)
    if not isinstance(value, int | float):
        raise ValueError(f"{prefix}.venue.{key} is required")


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} is required")
    return value


def _optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value
