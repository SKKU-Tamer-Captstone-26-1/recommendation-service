"""Seed venue inventory from a local map snapshot fixture.

This is a local dummy-test helper only. It must not read map-service databases.
Production map/place data must arrive through map-service APIs, events, or
snapshot feeds and then flow through MapSnapshotImportService.
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal  # noqa: E402
from app.models.catalog import BeverageItem  # noqa: E402
from app.services.map_snapshot_import import MapSnapshotImportService  # noqa: E402
from app.services.map_snapshot_sync import parse_map_snapshot_event_page  # noqa: E402

DEFAULT_FIXTURE = Path("data/map/venue_inventory_seed_events.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    args = parser.parse_args()

    if not args.fixture.exists():
        raise SystemExit(
            "fixture file is required. Provide a map_snapshot_event_v1 page with "
            f"--fixture <path>; default not found: {args.fixture}",
        )

    page = load_snapshot_page(args.fixture)
    parsed = parse_map_snapshot_event_page(page)

    with SessionLocal() as session:
        importer = MapSnapshotImportService(session)
        try:
            events = [resolve_beverage_names(session, event) for event in parsed.events]
            results = [importer.import_snapshot_event(event) for event in events]
            session.commit()
        except Exception:
            session.rollback()
            raise

    print(
        "venue inventory fixture seed "
        f"fixture={args.fixture} "
        f"events={len(results)} "
        f"venues_created={sum(1 for result in results if result.venue_created)} "
        f"inventory_created={sum(result.inventory_created for result in results)} "
        f"prices_created={sum(result.prices_created for result in results)}",
    )
    return 0


def load_snapshot_page(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("snapshot fixture must contain one JSON object")
    return payload


def resolve_beverage_names(
    session: Session,
    event: dict[str, Any],
) -> dict[str, Any]:
    """Resolve fixture-only beverage names to canonical beverage_item_id values."""

    resolved = deepcopy(event)
    name_index = _beverage_name_index(session)
    for lane in ("menus", "inventory", "prices"):
        rows = resolved.get(lane, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict) or row.get("beverage_item_id"):
                continue
            name = row.get("beverage_name_en") or row.get("canonical_name_en")
            if not isinstance(name, str) or not name:
                continue
            beverage_id = name_index.get(name)
            if beverage_id is None:
                raise ValueError(f"active beverage not found for fixture name: {name}")
            row["beverage_item_id"] = str(beverage_id)
            row.setdefault("source_beverage_id", name)
    return resolved


def _beverage_name_index(session: Session) -> dict[str, Any]:
    rows = session.scalars(
        select(BeverageItem).where(BeverageItem.active.is_(True)),
    )
    return {row.name_en: row.id for row in rows if row.name_en}


if __name__ == "__main__":
    raise SystemExit(main())
