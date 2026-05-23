import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JsonDict, TimestampMixin, UUIDPrimaryKeyMixin

STAGING_SCHEMA = "recommendation_staging"


class BeverageCollectionRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "beverage_collection_runs"
    __table_args__ = (
        {"schema": STAGING_SCHEMA},
    )

    run_id: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    agent: Mapped[str | None] = mapped_column(String(180), nullable=True)
    task_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    source_manifest_json: Mapped[JsonDict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    import_status: Mapped[str] = mapped_column(String(50), nullable=False)
    imported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    catalog_candidates = relationship(
        "BeverageCatalogCandidate",
        back_populates="collection_run",
        cascade="all, delete-orphan",
    )


class BeverageCandidateMixin(TimestampMixin):
    collection_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            f"{STAGING_SCHEMA}.beverage_collection_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    candidate_id: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    beverage_candidate_id: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )
    canonical_name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    candidate_status: Mapped[str] = mapped_column(String(50), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(50), nullable=False)
    validation_errors_json: Mapped[JsonDict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    raw_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)


class BeverageCatalogCandidate(
    UUIDPrimaryKeyMixin,
    BeverageCandidateMixin,
    Base,
):
    __tablename__ = "beverage_catalog_candidates"
    __table_args__ = (
        Index(
            "ix_beverage_catalog_candidates_category",
            "category",
            "validation_status",
        ),
        {"schema": STAGING_SCHEMA},
    )

    collection_run = relationship(
        "BeverageCollectionRun",
        back_populates="catalog_candidates",
    )


class BeverageFlavorProfileCandidate(
    UUIDPrimaryKeyMixin,
    BeverageCandidateMixin,
    Base,
):
    __tablename__ = "beverage_flavor_profile_candidates"
    __table_args__ = (
        Index(
            "ix_beverage_flavor_candidates_beverage",
            "beverage_candidate_id",
            "validation_status",
        ),
        {"schema": STAGING_SCHEMA},
    )


class BeverageKnowledgeCandidate(
    UUIDPrimaryKeyMixin,
    BeverageCandidateMixin,
    Base,
):
    __tablename__ = "beverage_knowledge_candidates"
    __table_args__ = (
        Index(
            "ix_beverage_knowledge_candidates_beverage",
            "beverage_candidate_id",
            "validation_status",
        ),
        {"schema": STAGING_SCHEMA},
    )

    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(80), nullable=True)


class BeveragePriceObservationCandidate(
    UUIDPrimaryKeyMixin,
    BeverageCandidateMixin,
    Base,
):
    __tablename__ = "beverage_price_observation_candidates"
    __table_args__ = (
        Index(
            "ix_beverage_price_candidates_market",
            "market_region",
            "currency",
            "validation_status",
        ),
        {"schema": STAGING_SCHEMA},
    )

    market_region: Mapped[str | None] = mapped_column(String(40), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    price_value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    observed_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class BeverageSourceRef(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "beverage_source_refs"
    __table_args__ = (
        Index("ix_beverage_source_refs_url", "url"),
        {"schema": STAGING_SCHEMA},
    )

    collection_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            f"{STAGING_SCHEMA}.beverage_collection_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    usage_lanes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_confidence: Mapped[str | None] = mapped_column(String(50), nullable=True)
    retrieved_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    raw_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)


class BeverageCandidateImportError(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "beverage_candidate_import_errors"
    __table_args__ = (
        Index(
            "ix_beverage_candidate_import_errors_run",
            "collection_run_id",
            "candidate_lane",
        ),
        {"schema": STAGING_SCHEMA},
    )

    collection_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            f"{STAGING_SCHEMA}.beverage_collection_runs.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    candidate_lane: Mapped[str] = mapped_column(String(80), nullable=False)
    candidate_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    error_code: Mapped[str] = mapped_column(String(100), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_json: Mapped[JsonDict | None] = mapped_column(JSONB, nullable=True)
