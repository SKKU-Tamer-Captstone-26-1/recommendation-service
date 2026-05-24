"""Run one map snapshot sync page from map-service into recommendation read models."""

from __future__ import annotations

import argparse

from app.db.session import SessionLocal
from app.services.map_snapshot_sync import HttpMapSnapshotClient, MapSnapshotSyncService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-name", default="map-service")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    with SessionLocal() as session:
        sync = MapSnapshotSyncService(session, HttpMapSnapshotClient())
        try:
            result = sync.sync_once(source_name=args.source_name, limit=args.limit)
            session.commit()
        except Exception:
            session.rollback()
            raise

    print(
        "map snapshot sync "
        f"source={result.source_name} "
        f"previous_cursor={result.previous_cursor} "
        f"next_cursor={result.next_cursor} "
        f"has_more={result.has_more} "
        f"watermark={result.snapshot_watermark} "
        f"events={result.events_received} "
        f"processed={result.events_processed} "
        f"duplicates={result.duplicate_events} "
        f"venues_created={result.venues_created} "
        f"menus_created={result.menus_created} "
        f"inventory_created={result.inventory_created} "
        f"prices_created={result.prices_created}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
