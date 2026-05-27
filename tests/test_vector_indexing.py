import uuid
from datetime import datetime
from typing import Any

import pytest
from qdrant_client import QdrantClient

from app.core.config import Settings
from app.infrastructure.qdrant import client as qdrant_client_module
from app.infrastructure.qdrant.client import (
    QdrantVectorClient,
    QdrantVectorPoint,
)
from app.models.enums import QdrantIndexStatus, VectorOwnerType
from app.models.vector import QdrantPoint, RecommendationVector
from app.models.versioning import VectorSchemaVersion
from app.services.vector_indexing import (
    VectorIndexingError,
    VectorIndexingService,
    build_indexable_vector_point,
    collection_for_owner_type,
)


def test_indexable_vector_point_is_deterministic_and_qdrant_compatible() -> None:
    vector_schema = _vector_schema(dimension_count=2)
    vector = _vector(values=[0.1, 0.2], schema_id=vector_schema.id)

    first = build_indexable_vector_point(
        collection_name="beverage_vectors_v1",
        vector=vector,
        vector_schema=vector_schema,
        owner_payload={"category": "whiskey", "active": True},
    )
    second = build_indexable_vector_point(
        collection_name="beverage_vectors_v1",
        vector=vector,
        vector_schema=vector_schema,
        owner_payload={"category": "whiskey", "active": True},
    )

    assert first.point_id == second.point_id
    assert first.payload_hash == second.payload_hash
    assert first.payload["owner_id"] == str(vector.owner_id)
    assert first.payload["category"] == "whiskey"
    uuid.UUID(first.point_id)


def test_index_owner_type_upserts_qdrant_and_metadata() -> None:
    schema = _vector_schema(dimension_count=2)
    vector = _vector(values=[0.1, 0.2], schema_id=schema.id)
    repository = _FakeVectorRepository(schema=schema, vectors=(vector,))
    qdrant = _FakeQdrantClient()

    result = VectorIndexingService(
        repository=repository,
        qdrant_client=qdrant,
        settings=Settings(qdrant_beverage_collection="beverage_vectors_v1"),
    ).index_owner_type(owner_type=VectorOwnerType.BEVERAGE_ITEM.value)

    assert result.scanned_count == 1
    assert result.indexed_count == 1
    assert result.failed_count == 0
    assert qdrant.ensured == [("beverage_vectors_v1", 2, "cosine")]
    assert len(qdrant.upserts) == 1

    stored_point = next(iter(repository.points.values()))
    assert stored_point.vector_id == vector.id
    assert stored_point.index_status == QdrantIndexStatus.INDEXED.value
    assert stored_point.last_error is None
    assert stored_point.indexed_at is not None


def test_index_owner_type_skips_unchanged_indexed_payload() -> None:
    schema = _vector_schema(dimension_count=2)
    vector = _vector(values=[0.1, 0.2], schema_id=schema.id)
    existing = build_indexable_vector_point(
        collection_name="beverage_vectors_v1",
        vector=vector,
        vector_schema=schema,
    )
    repository = _FakeVectorRepository(schema=schema, vectors=(vector,))
    repository.upsert_qdrant_point_metadata(
        vector_id=vector.id,
        collection_name=existing.collection_name,
        point_id=existing.point_id,
        payload_hash=existing.payload_hash,
        index_status=QdrantIndexStatus.INDEXED.value,
        payload_json=existing.payload,
        indexed_at=datetime.now(),
        last_error=None,
    )
    qdrant = _FakeQdrantClient()

    result = VectorIndexingService(
        repository=repository,
        qdrant_client=qdrant,
        settings=Settings(qdrant_beverage_collection="beverage_vectors_v1"),
    ).index_owner_type(owner_type=VectorOwnerType.BEVERAGE_ITEM.value)

    assert result.indexed_count == 0
    assert result.skipped_count == 1
    assert qdrant.upserts == []


def test_qdrant_upsert_failure_marks_point_failed() -> None:
    schema = _vector_schema(dimension_count=2)
    vector = _vector(values=[0.1, 0.2], schema_id=schema.id)
    repository = _FakeVectorRepository(schema=schema, vectors=(vector,))
    qdrant = _FakeQdrantClient(upsert_error=RuntimeError("qdrant unavailable"))

    result = VectorIndexingService(
        repository=repository,
        qdrant_client=qdrant,
        settings=Settings(qdrant_beverage_collection="beverage_vectors_v1"),
    ).index_owner_type(owner_type=VectorOwnerType.BEVERAGE_ITEM.value)

    assert result.failed_count == 1
    stored_point = next(iter(repository.points.values()))
    assert stored_point.index_status == QdrantIndexStatus.FAILED.value
    assert stored_point.indexed_at is None
    assert "qdrant unavailable" in (stored_point.last_error or "")


def test_dimension_mismatch_marks_failed_without_qdrant_upsert() -> None:
    schema = _vector_schema(dimension_count=3)
    vector = _vector(values=[0.1, 0.2], schema_id=schema.id)
    repository = _FakeVectorRepository(schema=schema, vectors=(vector,))
    qdrant = _FakeQdrantClient()

    result = VectorIndexingService(
        repository=repository,
        qdrant_client=qdrant,
        settings=Settings(qdrant_beverage_collection="beverage_vectors_v1"),
    ).index_owner_type(owner_type=VectorOwnerType.BEVERAGE_ITEM.value)

    assert result.failed_count == 1
    assert qdrant.upserts == []
    stored_point = next(iter(repository.points.values()))
    assert stored_point.index_status == QdrantIndexStatus.FAILED.value
    assert "dimension mismatch" in (stored_point.last_error or "")


def test_rebuild_recreate_forces_upsert_even_when_payload_is_unchanged() -> None:
    schema = _vector_schema(dimension_count=2)
    vector = _vector(values=[0.1, 0.2], schema_id=schema.id)
    existing = build_indexable_vector_point(
        collection_name="beverage_vectors_v1",
        vector=vector,
        vector_schema=schema,
    )
    repository = _FakeVectorRepository(schema=schema, vectors=(vector,))
    repository.upsert_qdrant_point_metadata(
        vector_id=vector.id,
        collection_name=existing.collection_name,
        point_id=existing.point_id,
        payload_hash=existing.payload_hash,
        index_status=QdrantIndexStatus.INDEXED.value,
        payload_json=existing.payload,
        indexed_at=datetime.now(),
        last_error=None,
    )
    qdrant = _FakeQdrantClient()

    result = VectorIndexingService(
        repository=repository,
        qdrant_client=qdrant,
        settings=Settings(qdrant_beverage_collection="beverage_vectors_v1"),
    ).rebuild_collection(
        owner_type=VectorOwnerType.BEVERAGE_ITEM.value,
        recreate=True,
    )

    assert result.indexed_count == 1
    assert qdrant.recreated == [("beverage_vectors_v1", 2, "cosine")]
    assert len(qdrant.upserts) == 1


def test_collection_for_owner_type_uses_configured_collections() -> None:
    settings = Settings(qdrant_profile_collection="profiles")

    assert (
        collection_for_owner_type(settings, VectorOwnerType.PROFILE_REVISION.value)
        == "profiles"
    )
    with pytest.raises(VectorIndexingError):
        collection_for_owner_type(settings, "unknown_owner")


def test_qdrant_vector_client_indexes_and_queries_in_memory() -> None:
    qdrant = QdrantVectorClient(QdrantClient(":memory:"))
    qdrant.ensure_collection(
        collection_name="test_vectors",
        vector_size=2,
        distance_metric="cosine",
    )
    qdrant.ensure_collection(
        collection_name="test_vectors",
        vector_size=2,
        distance_metric="cosine",
    )
    qdrant.upsert_points(
        collection_name="test_vectors",
        points=(
            QdrantVectorPoint(
                point_id="11111111-1111-4111-8111-111111111111",
                vector=[0.1, 0.2],
                payload={"owner_type": "beverage_item"},
            ),
        ),
    )

    results = qdrant.query_nearest(
        collection_name="test_vectors",
        vector=[0.1, 0.2],
        limit=1,
    )

    assert results[0].point_id == "11111111-1111-4111-8111-111111111111"
    assert results[0].payload["owner_type"] == "beverage_item"
    assert results[0].score > 0.99


def test_create_qdrant_client_does_not_force_default_port(monkeypatch) -> None:
    captured_kwargs: dict[str, Any] = {}

    class FakeQdrantClient:
        def __init__(self, **kwargs) -> None:
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(qdrant_client_module, "QdrantClient", FakeQdrantClient)

    qdrant_client_module.create_qdrant_client(
        Settings(
            qdrant_url="https://recommendation-qdrant-staging.example.run.app",
            qdrant_api_key="secret",
        ),
    )

    assert captured_kwargs["url"] == (
        "https://recommendation-qdrant-staging.example.run.app"
    )
    assert captured_kwargs["port"] is None


class _FakeVectorRepository:
    def __init__(
        self,
        *,
        schema: VectorSchemaVersion,
        vectors: tuple[RecommendationVector, ...],
    ) -> None:
        self.schema = schema
        self.vectors = vectors
        self.points: dict[tuple[str, str], QdrantPoint] = {}

    def get_active_vector_schema(
        self,
        version: str,
    ) -> VectorSchemaVersion | None:
        if version == self.schema.version:
            return self.schema
        return None

    def list_vectors(
        self,
        *,
        owner_type: str,
        vector_schema_version_id: uuid.UUID,
        limit: int | None = None,
    ) -> tuple[RecommendationVector, ...]:
        matched = tuple(
            vector
            for vector in self.vectors
            if vector.owner_type == owner_type
            and vector.vector_schema_version_id == vector_schema_version_id
        )
        if limit is None:
            return matched
        return matched[:limit]

    def get_qdrant_point(
        self,
        *,
        collection_name: str,
        point_id: str,
    ) -> QdrantPoint | None:
        return self.points.get((collection_name, point_id))

    def upsert_qdrant_point_metadata(
        self,
        *,
        vector_id: uuid.UUID,
        collection_name: str,
        point_id: str,
        payload_hash: str,
        index_status: str,
        payload_json: dict[str, Any],
        indexed_at: datetime | None,
        last_error: str | None,
    ) -> QdrantPoint:
        key = (collection_name, point_id)
        point = self.points.get(key)
        if point is None:
            point = QdrantPoint(
                vector_id=vector_id,
                collection_name=collection_name,
                point_id=point_id,
                payload_hash=payload_hash,
                index_status=index_status,
                payload_json=payload_json,
                indexed_at=indexed_at,
                last_error=last_error,
            )
            self.points[key] = point
            return point

        point.vector_id = vector_id
        point.payload_hash = payload_hash
        point.index_status = index_status
        point.payload_json = payload_json
        point.indexed_at = indexed_at
        point.last_error = last_error
        return point


class _FakeQdrantClient:
    def __init__(self, upsert_error: Exception | None = None) -> None:
        self.upsert_error = upsert_error
        self.ensured: list[tuple[str, int, str]] = []
        self.recreated: list[tuple[str, int, str]] = []
        self.upserts: list[tuple[str, tuple[QdrantVectorPoint, ...]]] = []

    def ensure_collection(
        self,
        *,
        collection_name: str,
        vector_size: int,
        distance_metric: str,
    ) -> None:
        self.ensured.append((collection_name, vector_size, distance_metric))

    def recreate_collection(
        self,
        *,
        collection_name: str,
        vector_size: int,
        distance_metric: str,
    ) -> None:
        self.recreated.append((collection_name, vector_size, distance_metric))

    def upsert_points(
        self,
        *,
        collection_name: str,
        points: tuple[QdrantVectorPoint, ...],
    ) -> None:
        if self.upsert_error is not None:
            raise self.upsert_error
        self.upserts.append((collection_name, points))


def _vector_schema(dimension_count: int) -> VectorSchemaVersion:
    return VectorSchemaVersion(
        id=uuid.uuid4(),
        name="taste",
        version="taste_v1",
        dimensions_json={},
        dimension_count=dimension_count,
        distance_metric="cosine",
        status="active",
    )


def _vector(values: list[float], schema_id: uuid.UUID) -> RecommendationVector:
    return RecommendationVector(
        id=uuid.uuid4(),
        owner_type=VectorOwnerType.BEVERAGE_ITEM.value,
        owner_id=uuid.uuid4(),
        vector_schema_version_id=schema_id,
        vector=values,
        vector_json={},
        confidence_json={},
        source_hash="source_hash",
        source_metadata_json={},
    )
