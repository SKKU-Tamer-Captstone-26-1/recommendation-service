import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JsonDict, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import RebuildJobStatus


class RebuildJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rebuild_jobs"
    __table_args__ = (
        Index("ix_rebuild_jobs_status_created", "status", "created_at"),
    )

    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    scope_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=RebuildJobStatus.PENDING.value,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    requested_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)

    items = relationship(
        "RebuildJobItem",
        back_populates="job",
        cascade="all, delete-orphan",
    )


class RebuildJobItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rebuild_job_items"
    __table_args__ = (
        Index("ix_rebuild_job_items_job_status", "job_id", "status"),
        Index("ix_rebuild_job_items_target", "target_type", "target_id"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rebuild_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=RebuildJobStatus.PENDING.value,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)

    job = relationship("RebuildJob", back_populates="items")

