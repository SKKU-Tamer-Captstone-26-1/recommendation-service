import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JsonDict, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SyncEventStatus


class SurveySyncCursor(TimestampMixin, Base):
    __tablename__ = "survey_sync_cursors"

    source_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    cursor_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    metadata_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)


class MapSnapshotSyncCursor(TimestampMixin, Base):
    __tablename__ = "map_snapshot_sync_cursors"

    source_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    cursor_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    metadata_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)


class SurveySyncEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "survey_sync_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_survey_sync_events_event_id"),
        Index("ix_survey_sync_events_status_retry", "status", "next_retry_at"),
        Index("ix_survey_sync_events_survey_response", "survey_response_id"),
    )

    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    external_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    survey_response_id: Mapped[str] = mapped_column(String(128), nullable=False)
    survey_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    response_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    event_payload_json: Mapped[JsonDict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=SyncEventStatus.PENDING.value,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    dead_letters = relationship(
        "DeadLetterEvent",
        back_populates="sync_event",
        cascade="all, delete-orphan",
    )


class MapSnapshotSyncEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "map_snapshot_sync_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_map_snapshot_sync_events_event_id"),
        Index("ix_map_snapshot_sync_events_status_retry", "status", "next_retry_at"),
        Index("ix_map_snapshot_sync_events_place", "place_id"),
    )

    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    place_id: Mapped[str] = mapped_column(String(128), nullable=False)
    place_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    menu_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    inventory_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    price_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_payload_json: Mapped[JsonDict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=SyncEventStatus.PENDING.value,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DeadLetterEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dead_letter_events"
    __table_args__ = (
        Index("ix_dead_letter_events_event_id", "event_id"),
    )

    sync_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("survey_sync_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    event_payload_json: Mapped[JsonDict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    dead_letter_reason: Mapped[str] = mapped_column(Text, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    sync_event = relationship("SurveySyncEvent", back_populates="dead_letters")
