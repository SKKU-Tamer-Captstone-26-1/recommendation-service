from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.infrastructure.qdrant.client import QdrantVectorClient, QdrantVectorPoint
from app.models.catalog import BeverageItem
from app.models.enums import QdrantIndexStatus, VectorOwnerType
from app.models.profile import TasteProfileRevision
from app.models.vector import QdrantPoint, RecommendationVector
from app.models.versioning import VectorSchemaVersion
from app.repositories.vectors import VectorRepository

QDRANT_POINT_NAMESPACE = uuid.UUID("4f927b4d-ec0d-5f67-88be-9b8c70e74d85")


class VectorIndexingError(RuntimeError):
    """Raised when canonical vectors cannot be indexed safely."""


class QdrantVectorClientProtocol(Protocol):
    def ensure_collection(
        self,
        *,
        collection_name: str,
        vector_size: int,
        distance_metric: str,
    ) -> None: ...

    def recreate_collection(
        self,
        *,
        collection_name: str,
        vector_size: int,
        distance_metric: str,
    ) -> None: ...

    def upsert_points(
        self,
        *,
        collection_name: str,
        points: tuple[QdrantVectorPoint, ...],
    ) -> None: ...


class VectorIndexRepositoryProtocol(Protocol):
    def get_active_vector_schema(
        self,
        version: str,
    ) -> VectorSchemaVersion | None: ...

    def list_vectors(
        self,
        *,
        owner_type: str,
        vector_schema_version_id: uuid.UUID,
        limit: int | None = None,
    ) -> tuple[RecommendationVector, ...]: ...

    def get_qdrant_point(
        self,
        *,
        collection_name: str,
        point_id: str,
    ) -> QdrantPoint | None: ...

    def upsert_qdrant_point_metadata(
        self,
        *,
        vector_id: uuid.UUID,
        collection_name: str,
        point_id: str,
        payload_hash: str,
        index_status: str,
        payload_json: dict[str, object],
        indexed_at: datetime | None,
        last_error: str | None,
    ) -> QdrantPoint: ...


@dataclass(frozen=True)
class IndexableVectorPoint:
    collection_name: str
    point_id: str
    point_key: str
    vector_id: uuid.UUID
    vector: list[float]
    payload: dict[str, object]
    payload_hash: str


@dataclass(frozen=True)
class VectorIndexingResult:
    owner_type: str
    collection_name: str
    vector_schema_version: str
    scanned_count: int
    indexed_count: int
    skipped_count: int
    failed_count: int
    dry_run: bool = False


class VectorIndexingService:
    """Indexes PostgreSQL-canonical recommendation vectors into Qdrant."""

    def __init__(
        self,
        *,
        repository: VectorIndexRepositoryProtocol,
        qdrant_client: QdrantVectorClientProtocol,
        settings: Settings | None = None,
        session: Session | None = None,
    ) -> None:
        self._repository = repository
        self._qdrant_client = qdrant_client
        self._settings = settings or get_settings()
        self._session = session

    @classmethod
    def from_session(
        cls,
        session: Session,
        qdrant_client: QdrantVectorClient,
        settings: Settings | None = None,
    ) -> VectorIndexingService:
        return cls(
            repository=VectorRepository(session),
            qdrant_client=qdrant_client,
            settings=settings,
            session=session,
        )

    def index_owner_type(
        self,
        *,
        owner_type: str,
        vector_schema_version: str | None = None,
        limit: int | None = None,
        dry_run: bool = False,
        create_collection: bool = True,
        force: bool = False,
    ) -> VectorIndexingResult:
        schema_version = vector_schema_version or self._settings.active_vector_schema
        vector_schema = self._require_vector_schema(schema_version)
        collection_name = collection_for_owner_type(self._settings, owner_type)
        vectors = self._repository.list_vectors(
            owner_type=owner_type,
            vector_schema_version_id=vector_schema.id,
            limit=limit,
        )
        return self.index_vectors(
            owner_type=owner_type,
            vectors=vectors,
            vector_schema=vector_schema,
            collection_name=collection_name,
            dry_run=dry_run,
            create_collection=create_collection,
            force=force,
        )

    def rebuild_collection(
        self,
        *,
        owner_type: str,
        vector_schema_version: str | None = None,
        limit: int | None = None,
        recreate: bool = False,
        dry_run: bool = False,
    ) -> VectorIndexingResult:
        schema_version = vector_schema_version or self._settings.active_vector_schema
        vector_schema = self._require_vector_schema(schema_version)
        collection_name = collection_for_owner_type(self._settings, owner_type)

        if recreate and not dry_run:
            self._qdrant_client.recreate_collection(
                collection_name=collection_name,
                vector_size=vector_schema.dimension_count,
                distance_metric=vector_schema.distance_metric,
            )

        vectors = self._repository.list_vectors(
            owner_type=owner_type,
            vector_schema_version_id=vector_schema.id,
            limit=limit,
        )
        return self.index_vectors(
            owner_type=owner_type,
            vectors=vectors,
            vector_schema=vector_schema,
            collection_name=collection_name,
            dry_run=dry_run,
            create_collection=not recreate,
            force=recreate,
        )

    def index_vectors(
        self,
        *,
        owner_type: str,
        vectors: tuple[RecommendationVector, ...],
        vector_schema: VectorSchemaVersion,
        collection_name: str,
        dry_run: bool = False,
        create_collection: bool = True,
        force: bool = False,
    ) -> VectorIndexingResult:
        if create_collection and not dry_run:
            self._qdrant_client.ensure_collection(
                collection_name=collection_name,
                vector_size=vector_schema.dimension_count,
                distance_metric=vector_schema.distance_metric,
            )

        indexed_count = 0
        skipped_count = 0
        failed_count = 0

        for vector in vectors:
            point = build_indexable_vector_point(
                collection_name=collection_name,
                vector=vector,
                vector_schema=vector_schema,
                owner_payload=self._owner_payload(vector),
            )
            existing = self._repository.get_qdrant_point(
                collection_name=collection_name,
                point_id=point.point_id,
            )

            dimension_error = _dimension_error(vector, vector_schema)
            if dimension_error is not None:
                failed_count += 1
                if not dry_run:
                    self._mark_failed(point, dimension_error)
                continue

            if _can_skip(existing, point.payload_hash, force):
                skipped_count += 1
                continue

            if dry_run:
                skipped_count += 1
                continue

            try:
                self._qdrant_client.upsert_points(
                    collection_name=collection_name,
                    points=(
                        QdrantVectorPoint(
                            point_id=point.point_id,
                            vector=point.vector,
                            payload=point.payload,
                        ),
                    ),
                )
            except Exception as exc:
                failed_count += 1
                self._mark_failed(point, str(exc))
                continue

            self._repository.upsert_qdrant_point_metadata(
                vector_id=point.vector_id,
                collection_name=point.collection_name,
                point_id=point.point_id,
                payload_hash=point.payload_hash,
                index_status=QdrantIndexStatus.INDEXED.value,
                payload_json=point.payload,
                indexed_at=datetime.now(UTC),
                last_error=None,
            )
            indexed_count += 1

        return VectorIndexingResult(
            owner_type=owner_type,
            collection_name=collection_name,
            vector_schema_version=vector_schema.version,
            scanned_count=len(vectors),
            indexed_count=indexed_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            dry_run=dry_run,
        )

    def _require_vector_schema(self, version: str) -> VectorSchemaVersion:
        vector_schema = self._repository.get_active_vector_schema(version)
        if vector_schema is None:
            raise VectorIndexingError(f"active vector schema not found: {version}")
        return vector_schema

    def _owner_payload(self, vector: RecommendationVector) -> dict[str, object]:
        if self._session is None:
            return {}

        if vector.owner_type == VectorOwnerType.BEVERAGE_ITEM.value:
            beverage = self._session.get(BeverageItem, vector.owner_id)
            if beverage is None:
                return {}
            return {
                "category": beverage.category,
                "active": beverage.active,
                "catalog_key": (beverage.metadata_json or {}).get("catalog_key"),
            }

        if vector.owner_type == VectorOwnerType.PROFILE_REVISION.value:
            profile = self._session.get(TasteProfileRevision, vector.owner_id)
            if profile is None:
                return {}
            return {
                "profile_revision": profile.profile_revision,
                "status": profile.status,
            }

        return {}

    def _mark_failed(self, point: IndexableVectorPoint, error: str) -> None:
        self._repository.upsert_qdrant_point_metadata(
            vector_id=point.vector_id,
            collection_name=point.collection_name,
            point_id=point.point_id,
            payload_hash=point.payload_hash,
            index_status=QdrantIndexStatus.FAILED.value,
            payload_json=point.payload,
            indexed_at=None,
            last_error=error[:2000],
        )


def collection_for_owner_type(settings: Settings, owner_type: str) -> str:
    if owner_type == VectorOwnerType.BEVERAGE_ITEM.value:
        return settings.qdrant_beverage_collection
    if owner_type == VectorOwnerType.PROFILE_REVISION.value:
        return settings.qdrant_profile_collection
    if owner_type == VectorOwnerType.VENUE_SNAPSHOT.value:
        return settings.qdrant_venue_collection
    if owner_type == VectorOwnerType.VENUE_MENU_SNAPSHOT.value:
        return settings.qdrant_menu_item_collection
    raise VectorIndexingError(f"unsupported vector owner type: {owner_type}")


def build_indexable_vector_point(
    *,
    collection_name: str,
    vector: RecommendationVector,
    vector_schema: VectorSchemaVersion,
    owner_payload: dict[str, object] | None = None,
) -> IndexableVectorPoint:
    point_key = (
        f"{vector_schema.version}:{vector.owner_type}:"
        f"{vector.owner_id}:{vector.id}"
    )
    point_id = str(uuid.uuid5(QDRANT_POINT_NAMESPACE, point_key))
    payload = {
        "point_key": point_key,
        "vector_id": str(vector.id),
        "owner_type": vector.owner_type,
        "owner_id": str(vector.owner_id),
        "vector_schema_name": vector_schema.name,
        "vector_schema_version": vector_schema.version,
        "source_hash": vector.source_hash,
    }
    if owner_payload:
        payload.update(
            {
                key: value
                for key, value in owner_payload.items()
                if value is not None
            },
        )
    payload_hash = stable_payload_hash(
        {
            "payload": payload,
            "vector": [float(value) for value in vector.vector],
            "confidence": vector.confidence_json or {},
        },
    )
    return IndexableVectorPoint(
        collection_name=collection_name,
        point_id=point_id,
        point_key=point_key,
        vector_id=vector.id,
        vector=[float(value) for value in vector.vector],
        payload=payload,
        payload_hash=payload_hash,
    )


def stable_payload_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _dimension_error(
    vector: RecommendationVector,
    vector_schema: VectorSchemaVersion,
) -> str | None:
    actual = len(vector.vector)
    expected = vector_schema.dimension_count
    if actual == expected:
        return None
    return (
        f"vector dimension mismatch for vector_id={vector.id}: "
        f"expected={expected} actual={actual}"
    )


def _can_skip(
    existing: QdrantPoint | None,
    payload_hash: str,
    force: bool,
) -> bool:
    return (
        not force
        and existing is not None
        and existing.payload_hash == payload_hash
        and existing.index_status == QdrantIndexStatus.INDEXED.value
    )
