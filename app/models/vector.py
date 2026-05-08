import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JsonDict, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import QdrantIndexStatus


class RecommendationVector(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recommendation_vectors"
    __table_args__ = (
        UniqueConstraint(
            "owner_type",
            "owner_id",
            "vector_schema_version_id",
            "source_hash",
            name="uq_recommendation_vector_identity",
        ),
        Index(
            "ix_recommendation_vectors_owner",
            "owner_type",
            "owner_id",
            "vector_schema_version_id",
        ),
    )

    owner_type: Mapped[str] = mapped_column(String(50), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vector_schema_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vector_schema_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    vector: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)
    vector_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False)
    confidence_json: Mapped[JsonDict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    source_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    source_metadata_json: Mapped[JsonDict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    vector_schema = relationship("VectorSchemaVersion", back_populates="vectors")
    qdrant_points = relationship(
        "QdrantPoint",
        back_populates="vector",
        cascade="all, delete-orphan",
    )


class QdrantPoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "qdrant_points"
    __table_args__ = (
        UniqueConstraint(
            "collection_name",
            "point_id",
            name="uq_qdrant_collection_point",
        ),
        Index("ix_qdrant_points_vector_id", "vector_id"),
    )

    vector_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recommendation_vectors.id", ondelete="CASCADE"),
        nullable=False,
    )
    collection_name: Mapped[str] = mapped_column(String(128), nullable=False)
    point_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    index_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=QdrantIndexStatus.PENDING.value,
    )
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)

    vector = relationship("RecommendationVector", back_populates="qdrant_points")
