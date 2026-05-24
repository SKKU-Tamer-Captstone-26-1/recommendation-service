"""Rebuild a Qdrant collection from PostgreSQL-canonical vectors."""

from __future__ import annotations

import argparse

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.infrastructure.qdrant.client import create_qdrant_vector_client
from app.models.enums import VectorOwnerType
from app.services.vector_indexing import VectorIndexingService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--owner-type",
        required=True,
        choices=(
            VectorOwnerType.BEVERAGE_ITEM.value,
            VectorOwnerType.PROFILE_REVISION.value,
            VectorOwnerType.VENUE_SNAPSHOT.value,
            VectorOwnerType.VENUE_MENU_SNAPSHOT.value,
        ),
    )
    parser.add_argument("--schema", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--recreate", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    with SessionLocal() as session:
        service = VectorIndexingService.from_session(
            session,
            create_qdrant_vector_client(settings),
            settings,
        )
        try:
            result = service.rebuild_collection(
                owner_type=args.owner_type,
                vector_schema_version=args.schema,
                limit=args.limit,
                recreate=args.recreate,
                dry_run=args.dry_run,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise

    print(
        "qdrant rebuild "
        f"owner_type={result.owner_type} "
        f"collection={result.collection_name} "
        f"schema={result.vector_schema_version} "
        f"recreate={args.recreate} "
        f"scanned={result.scanned_count} "
        f"indexed={result.indexed_count} "
        f"skipped={result.skipped_count} "
        f"failed={result.failed_count} "
        f"dry_run={result.dry_run}",
    )
    return 1 if result.failed_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
