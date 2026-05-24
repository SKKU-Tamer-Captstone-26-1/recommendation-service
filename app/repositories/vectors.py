import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import ArtifactStatus
from app.models.vector import QdrantPoint, RecommendationVector
from app.models.versioning import VectorSchemaVersion


class VectorRepository:
    """Access to canonical vectors and rebuildable Qdrant metadata."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_vector_by_owner(
        self,
        *,
        owner_type: str,
        owner_id: uuid.UUID,
        vector_schema_version_id: uuid.UUID,
    ) -> RecommendationVector | None:
        statement = select(RecommendationVector).where(
            RecommendationVector.owner_type == owner_type,
            RecommendationVector.owner_id == owner_id,
            RecommendationVector.vector_schema_version_id == vector_schema_version_id,
        )
        return self._session.scalar(statement)

    def get_active_vector_schema(
        self,
        version: str,
    ) -> VectorSchemaVersion | None:
        statement = select(VectorSchemaVersion).where(
            VectorSchemaVersion.version == version,
            VectorSchemaVersion.status == ArtifactStatus.ACTIVE.value,
        )
        return self._session.scalar(statement)

    def list_vectors(
        self,
        *,
        owner_type: str,
        vector_schema_version_id: uuid.UUID,
        limit: int | None = None,
    ) -> tuple[RecommendationVector, ...]:
        statement = (
            select(RecommendationVector)
            .where(
                RecommendationVector.owner_type == owner_type,
                RecommendationVector.vector_schema_version_id
                == vector_schema_version_id,
            )
            .order_by(
                RecommendationVector.owner_type,
                RecommendationVector.owner_id,
                RecommendationVector.id,
            )
        )
        if limit is not None:
            statement = statement.limit(limit)
        return tuple(self._session.scalars(statement).all())

    def get_qdrant_point(
        self,
        *,
        collection_name: str,
        point_id: str,
    ) -> QdrantPoint | None:
        statement = select(QdrantPoint).where(
            QdrantPoint.collection_name == collection_name,
            QdrantPoint.point_id == point_id,
        )
        return self._session.scalar(statement)

    def list_qdrant_points(
        self,
        vector_id: uuid.UUID,
    ) -> tuple[QdrantPoint, ...]:
        statement = (
            select(QdrantPoint)
            .where(QdrantPoint.vector_id == vector_id)
            .order_by(QdrantPoint.collection_name, QdrantPoint.point_id)
        )
        return tuple(self._session.scalars(statement).all())

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
        point = self.get_qdrant_point(
            collection_name=collection_name,
            point_id=point_id,
        )
        if point is None:
            point = QdrantPoint(
                vector_id=vector_id,
                collection_name=collection_name,
                point_id=point_id,
                payload_hash=payload_hash,
                index_status=index_status,
                indexed_at=indexed_at,
                last_error=last_error,
                payload_json=payload_json,
            )
            self._session.add(point)
            return point

        point.vector_id = vector_id
        point.payload_hash = payload_hash
        point.index_status = index_status
        point.indexed_at = indexed_at
        point.last_error = last_error
        point.payload_json = payload_json
        return point
