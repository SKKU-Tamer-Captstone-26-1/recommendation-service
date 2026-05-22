from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import ArtifactStatus
from app.models.versioning import MapperVersion, ScoringConfig, VectorSchemaVersion


class VersioningRepository:
    """Read-only access to version registry metadata."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_active_vector_schema(
        self,
        version: str,
    ) -> VectorSchemaVersion | None:
        statement = select(VectorSchemaVersion).where(
            VectorSchemaVersion.version == version,
            VectorSchemaVersion.status == ArtifactStatus.ACTIVE.value,
        )
        return self._session.scalar(statement)

    def get_active_mapper_version(
        self,
        version: str,
    ) -> MapperVersion | None:
        statement = select(MapperVersion).where(
            MapperVersion.version == version,
            MapperVersion.status == ArtifactStatus.ACTIVE.value,
        )
        return self._session.scalar(statement)

    def get_active_scoring_config(
        self,
        *,
        version: str,
        target_type: str,
        category: str = "all",
    ) -> ScoringConfig | None:
        statement = select(ScoringConfig).where(
            ScoringConfig.version == version,
            ScoringConfig.target_type == target_type,
            ScoringConfig.category == category,
            ScoringConfig.status == ArtifactStatus.ACTIVE.value,
        )
        return self._session.scalar(statement)

    def list_active_scoring_configs(
        self,
        version: str,
    ) -> tuple[ScoringConfig, ...]:
        statement = (
            select(ScoringConfig)
            .where(
                ScoringConfig.version == version,
                ScoringConfig.status == ArtifactStatus.ACTIVE.value,
            )
            .order_by(ScoringConfig.target_type, ScoringConfig.category)
        )
        return tuple(self._session.scalars(statement).all())
