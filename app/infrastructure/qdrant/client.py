from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient, models

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class QdrantVectorPoint:
    point_id: str
    vector: list[float]
    payload: dict[str, Any]


@dataclass(frozen=True)
class QdrantSearchResult:
    point_id: str
    score: float
    payload: dict[str, Any]


class QdrantVectorClient:
    """Small adapter around qdrant-client for rebuildable vector indexes."""

    def __init__(self, client: QdrantClient) -> None:
        self._client = client

    def ensure_collection(
        self,
        *,
        collection_name: str,
        vector_size: int,
        distance_metric: str,
    ) -> None:
        if self._client.collection_exists(collection_name):
            self._validate_collection(
                collection_name=collection_name,
                vector_size=vector_size,
                distance_metric=distance_metric,
            )
            return

        self._client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=_qdrant_distance(distance_metric),
            ),
        )

    def recreate_collection(
        self,
        *,
        collection_name: str,
        vector_size: int,
        distance_metric: str,
    ) -> None:
        if self._client.collection_exists(collection_name):
            self._client.delete_collection(collection_name=collection_name)
        self._client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=_qdrant_distance(distance_metric),
            ),
        )

    def upsert_points(
        self,
        *,
        collection_name: str,
        points: tuple[QdrantVectorPoint, ...],
    ) -> None:
        if not points:
            return

        self._client.upsert(
            collection_name=collection_name,
            points=[
                models.PointStruct(
                    id=point.point_id,
                    vector=point.vector,
                    payload=point.payload,
                )
                for point in points
            ],
            wait=True,
        )

    def query_nearest(
        self,
        *,
        collection_name: str,
        vector: list[float],
        limit: int,
    ) -> tuple[QdrantSearchResult, ...]:
        response = self._client.query_points(
            collection_name=collection_name,
            query=vector,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return tuple(
            QdrantSearchResult(
                point_id=str(point.id),
                score=float(point.score),
                payload=dict(point.payload or {}),
            )
            for point in response.points
        )

    def _validate_collection(
        self,
        *,
        collection_name: str,
        vector_size: int,
        distance_metric: str,
    ) -> None:
        collection = self._client.get_collection(collection_name=collection_name)
        vector_params = collection.config.params.vectors
        if isinstance(vector_params, dict):
            if len(vector_params) != 1:
                raise ValueError(
                    f"collection {collection_name} uses named vectors; expected one",
                )
            vector_params = next(iter(vector_params.values()))

        actual_size = getattr(vector_params, "size", None)
        actual_distance = getattr(vector_params, "distance", None)
        expected_distance = _qdrant_distance(distance_metric)
        if actual_size != vector_size or actual_distance != expected_distance:
            raise ValueError(
                "Qdrant collection config mismatch for "
                f"{collection_name}: expected size={vector_size} "
                f"distance={expected_distance}, actual size={actual_size} "
                f"distance={actual_distance}",
            )


def create_qdrant_client(settings: Settings | None = None) -> QdrantClient:
    resolved_settings = settings or get_settings()
    return QdrantClient(
        url=resolved_settings.qdrant_url,
        port=None,
        api_key=resolved_settings.qdrant_api_key or None,
        timeout=resolved_settings.qdrant_timeout_seconds,
    )


def create_qdrant_vector_client(
    settings: Settings | None = None,
) -> QdrantVectorClient:
    return QdrantVectorClient(create_qdrant_client(settings))


def check_qdrant(settings: Settings | None = None) -> bool:
    resolved_settings = settings or get_settings()
    if not resolved_settings.qdrant_indexing_enabled:
        return True

    client = create_qdrant_client(resolved_settings)
    client.get_collections()
    return True


def _qdrant_distance(distance_metric: str) -> models.Distance:
    normalized = distance_metric.lower()
    if normalized == "cosine":
        return models.Distance.COSINE
    if normalized == "dot":
        return models.Distance.DOT
    if normalized == "euclidean":
        return models.Distance.EUCLID
    raise ValueError(f"unsupported Qdrant distance metric: {distance_metric}")
