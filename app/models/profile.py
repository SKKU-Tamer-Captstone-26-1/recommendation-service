import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JsonDict, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ProfileStatus


class UserProfileState(TimestampMixin, Base):
    __tablename__ = "user_profile_state"

    external_user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    active_profile_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "taste_profile_revisions.id",
            name="fk_user_profile_state_active_profile_revision",
            use_alter=True,
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ProfileStatus.MISSING.value,
    )
    last_survey_response_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    last_survey_response_revision: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    active_profile_revision = relationship(
        "TasteProfileRevision",
        foreign_keys=[active_profile_revision_id],
        post_update=True,
    )
    profile_revisions = relationship(
        "TasteProfileRevision",
        foreign_keys="TasteProfileRevision.external_user_id",
        back_populates="user_profile_state",
    )


class TasteProfileRevision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "taste_profile_revisions"
    __table_args__ = (
        UniqueConstraint(
            "external_user_id",
            "profile_revision",
            name="uq_profile_revision_per_user",
        ),
        UniqueConstraint(
            "external_user_id",
            "survey_response_id",
            "survey_response_revision",
            "mapper_version_id",
            name="uq_profile_generation_identity",
        ),
    )

    external_user_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("user_profile_state.external_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    profile_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    survey_response_id: Mapped[str] = mapped_column(String(128), nullable=False)
    survey_version: Mapped[str] = mapped_column(String(100), nullable=False)
    survey_response_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    mapper_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mapper_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    vector_schema_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vector_schema_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    scoring_config_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scoring_configs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    taste_vector: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)
    taste_vector_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False)
    confidence_json: Mapped[JsonDict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    preferred_categories: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
    )
    preferred_keywords: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
    )
    budget_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ProfileStatus.PENDING_GENERATION.value,
    )
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    generation_metadata_json: Mapped[JsonDict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    user_profile_state = relationship(
        "UserProfileState",
        foreign_keys=[external_user_id],
        back_populates="profile_revisions",
    )
    mapper_version = relationship("MapperVersion", back_populates="profile_revisions")
    vector_schema_version = relationship("VectorSchemaVersion")
    scoring_config = relationship("ScoringConfig")
    survey_snapshot = relationship(
        "SurveySourceSnapshot",
        back_populates="profile_revision",
        uselist=False,
        cascade="all, delete-orphan",
    )


class SurveySourceSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "survey_source_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "profile_revision_id",
            name="uq_survey_snapshot_profile_revision",
        ),
    )

    profile_revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("taste_profile_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    survey_response_id: Mapped[str] = mapped_column(String(128), nullable=False)
    survey_version: Mapped[str] = mapped_column(String(100), nullable=False)
    survey_response_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot_json: Mapped[JsonDict | None] = mapped_column(JSONB, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    profile_revision = relationship(
        "TasteProfileRevision",
        back_populates="survey_snapshot",
    )
