import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.vector import QdrantPoint, RecommendationVector


class VectorRepository:
    """Read-only access to canonical vectors and Qdrant indexing metadata."""

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
