import uuid

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JsonDict, TimestampMixin, UUIDPrimaryKeyMixin


class RecommendationRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recommendation_requests"
    __table_args__ = (
        Index(
            "ix_recommendation_requests_user_created",
            "external_user_id",
            "created_at",
        ),
        Index("ix_recommendation_requests_profile", "profile_revision_id"),
    )

    external_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("taste_profile_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    filters_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)
    scoring_config_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scoring_configs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    request_context_json: Mapped[JsonDict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    profile_revision = relationship("TasteProfileRevision")
    scoring_config = relationship(
        "ScoringConfig",
        back_populates="recommendation_requests",
    )
    results = relationship(
        "RecommendationResult",
        back_populates="request",
        cascade="all, delete-orphan",
    )


class RecommendationResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recommendation_results"
    __table_args__ = (
        Index("ix_recommendation_results_request_rank", "request_id", "rank"),
        Index("ix_recommendation_results_target", "target_type", "target_id"),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recommendation_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_breakdown_json: Mapped[JsonDict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    qdrant_point_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    request = relationship("RecommendationRequest", back_populates="results")
    explanations = relationship(
        "RecommendationExplanation",
        back_populates="result",
        cascade="all, delete-orphan",
    )
    interactions = relationship(
        "RecommendationInteraction",
        back_populates="result",
        cascade="all, delete-orphan",
    )


class RecommendationExplanation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recommendation_explanations"
    __table_args__ = (
        Index("ix_recommendation_explanations_result", "result_id"),
    )

    result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recommendation_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    reason_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
    )
    matched_dimensions_json: Mapped[JsonDict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    template_version: Mapped[str] = mapped_column(String(50), nullable=False)
    explanation_text: Mapped[str] = mapped_column(Text, nullable=False)
    debug_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)

    result = relationship("RecommendationResult", back_populates="explanations")


class RecommendationInteraction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recommendation_interactions"
    __table_args__ = (
        Index("ix_recommendation_interactions_result_event", "result_id", "event_type"),
        Index("ix_recommendation_interactions_created", "created_at"),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recommendation_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    result_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recommendation_results.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)
    result = relationship("RecommendationResult", back_populates="interactions")
