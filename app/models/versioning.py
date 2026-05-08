from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JsonDict, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ArtifactStatus, DistanceMetric


class VectorSchemaVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vector_schema_versions"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_vector_schema_name_version"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    dimensions_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False)
    dimension_count: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_metric: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DistanceMetric.COSINE.value,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ArtifactStatus.DRAFT.value,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    vectors = relationship("RecommendationVector", back_populates="vector_schema")


class MapperVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mapper_versions"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_mapper_name_version"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    compatible_vector_schema: Mapped[str] = mapped_column(String(100), nullable=False)
    code_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rules_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ArtifactStatus.DRAFT.value,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    profile_revisions = relationship(
        "TasteProfileRevision",
        back_populates="mapper_version",
    )


class ScoringConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scoring_configs"
    __table_args__ = (
        UniqueConstraint(
            "name",
            "version",
            "target_type",
            "category",
            name="uq_scoring_config_identity",
        ),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="all")
    weights_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)
    reason_code_rules_json: Mapped[JsonDict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ArtifactStatus.DRAFT.value,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    recommendation_requests = relationship(
        "RecommendationRequest",
        back_populates="scoring_config",
    )

