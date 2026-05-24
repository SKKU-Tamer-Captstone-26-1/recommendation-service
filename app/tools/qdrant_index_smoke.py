"""Smoke Qdrant indexing by querying the rebuilt collection."""

from __future__ import annotations

import argparse

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.infrastructure.qdrant.client import create_qdrant_vector_client
from app.models.enums import VectorOwnerType
from app.repositories.vectors import VectorRepository
from app.services.vector_indexing import (
    VectorIndexingService,
    collection_for_owner_type,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--owner-type",
        default=VectorOwnerType.BEVERAGE_ITEM.value,
        choices=(
            VectorOwnerType.BEVERAGE_ITEM.value,
            VectorOwnerType.PROFILE_REVISION.value,
        ),
    )
    parser.add_argument("--schema", default=None)
    args = parser.parse_args()

    settings = get_settings()
    qdrant = create_qdrant_vector_client(settings)
    schema_version = args.schema or settings.active_vector_schema
    collection_name = collection_for_owner_type(settings, args.owner_type)

    with SessionLocal() as session:
        repository = VectorRepository(session)
        vector_schema = repository.get_active_vector_schema(schema_version)
        if vector_schema is None:
            raise RuntimeError(f"active vector schema not found: {schema_version}")

        service = VectorIndexingService.from_session(session, qdrant, settings)
        result = service.index_owner_type(
            owner_type=args.owner_type,
            vector_schema_version=schema_version,
            limit=1,
            force=True,
        )
        session.commit()

        vectors = repository.list_vectors(
            owner_type=args.owner_type,
            vector_schema_version_id=vector_schema.id,
            limit=1,
        )
        if not vectors:
            raise RuntimeError(
                f"no canonical vectors found for owner_type={args.owner_type}",
            )

    search_results = qdrant.query_nearest(
        collection_name=collection_name,
        vector=[float(value) for value in vectors[0].vector],
        limit=1,
    )
    if not search_results:
        raise RuntimeError(f"Qdrant query returned no points: {collection_name}")

    print(
        "qdrant index smoke "
        f"owner_type={args.owner_type} "
        f"collection={collection_name} "
        f"schema={schema_version} "
        f"indexed={result.indexed_count} "
        f"failed={result.failed_count} "
        f"nearest_point_id={search_results[0].point_id} "
        f"score={search_results[0].score}",
    )
    return 1 if result.failed_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
