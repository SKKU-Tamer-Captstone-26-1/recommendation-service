"""Seed venue snapshots and inventory from canonical map-service markers.

Reads liquor-shop markers directly from map-service DB and creates:
  - VenueSnapshot  (one per canonical venue)
  - VenueInventorySnapshot  (links venue to canonical beverage_items)

Run once against local DBs:
    python scripts/seed_venue_inventory.py
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg
from psycopg.rows import dict_row
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.catalog import BeverageItem, VenueInventorySnapshot, VenueSnapshot

MAP_DB_URL = os.environ.get(
    "MAP_DATABASE_URL",
    "postgresql://map_user:map_pass@127.0.0.1:55433/map_service",
)

# Canonical liquor_shop place_ids from map-service (visibility='visible')
# Maps place_id → list of beverage_item canonical_name_en to stock
LIQUOR_SHOP_INVENTORY: dict[str, list[str]] = {
    "86633237-8df0-5a5d-ac9a-ab4f91a35fff": [  # 더몰트샵
        "The Macallan 12 Years Double Cask",
        "Glenfiddich 12 Year Old",
        "Laphroaig 10 Year Old",
        "Buffalo Trace Bourbon",
        "Jameson Irish Whiskey",
    ],
}

_VENUE_NS = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
_INV_NS   = uuid.UUID("b2c3d4e5-f6a7-8901-bcde-f01234567891")


def _stable(namespace: uuid.UUID, *parts: str) -> uuid.UUID:
    return uuid.uuid5(namespace, ":".join(parts))


def _fetch_liquor_shops() -> list[dict]:
    with psycopg.connect(MAP_DB_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id::text            AS place_id,
                    label               AS name,
                    layer_code          AS place_type,
                    COALESCE(
                        filter_json->>'road_address',
                        filter_json->>'address',
                        ''
                    )                   AS address,
                    published_revision::text AS place_revision
                FROM map_view.markers
                WHERE visibility = 'visible'
                  AND layer_code  = 'liquor_shop'
            """)
            return cur.fetchall()


def seed(session: Session) -> None:
    # Build beverage name → id index
    beverage_index: dict[str, uuid.UUID] = {
        row.name_en: row.id
        for row in session.scalars(select(BeverageItem).where(BeverageItem.active == True))  # noqa: E712
    }

    shops = _fetch_liquor_shops()
    print(f"Found {len(shops)} liquor_shop marker(s) in map-service")

    now = datetime.now(UTC)
    stale_after = now + timedelta(days=7)

    for shop in shops:
        place_id = shop["place_id"]
        place_revision = shop["place_revision"] or "seed_v1"

        # --- VenueSnapshot ---
        venue_id = _stable(_VENUE_NS, place_id)
        venue = VenueSnapshot(
            id=venue_id,
            place_id=place_id,
            place_revision=place_revision,
            name=shop["name"],
            place_type=shop["place_type"],
            address=shop["address"] or None,
            status="active",
            publication_status="published",
            snapshot_json={"seeded_by": "seed_venue_inventory.py", "source": "map_service"},
            source_event_id=f"seed:{place_id}",
            synced_at=now,
            stale_after=stale_after,
        )
        session.merge(venue)
        print(f"  venue: {shop['name']} ({place_id})")

        # --- VenueInventorySnapshot ---
        items = LIQUOR_SHOP_INVENTORY.get(place_id, [])
        created = 0
        for item_name in items:
            bev_id = beverage_index.get(item_name)
            if bev_id is None:
                print(f"    [skip] '{item_name}' not found in beverage_items")
                continue

            inv_id = _stable(_INV_NS, place_id, str(bev_id))
            inv = VenueInventorySnapshot(
                id=inv_id,
                venue_snapshot_id=venue_id,
                place_id=place_id,
                beverage_item_id=bev_id,
                source_beverage_id=str(bev_id),
                inventory_revision="seed_v1",
                availability_status="available",
                confidence=0.85,
                last_seen_at=now,
                expires_at=stale_after,
                synced_at=now,
                snapshot_json={"seeded_by": "seed_venue_inventory.py"},
            )
            session.merge(inv)
            created += 1
            print(f"    + {item_name}")

        print(f"    {created} inventory item(s) linked")

    session.commit()
    print("Done.")


if __name__ == "__main__":
    with Session(engine) as s:
        seed(s)
