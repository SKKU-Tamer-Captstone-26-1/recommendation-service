import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JsonDict, TimestampMixin, UUIDPrimaryKeyMixin


class BeverageItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "beverage_items"
    __table_args__ = (
        Index("ix_beverage_items_category_active", "category", "active"),
        Index("ix_beverage_items_price_range", "price_min_krw", "price_max_krw"),
        Index(
            "ix_beverage_items_search_document",
            "search_document",
            postgresql_using="gin",
        ),
    )

    category: Mapped[str] = mapped_column(String(100), nullable=False)
    name_ko: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    abv: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_min_krw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_max_krw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_document: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    metadata_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)

    menu_snapshots = relationship(
        "VenueMenuSnapshot",
        back_populates="beverage_item",
    )
    inventory_snapshots = relationship(
        "VenueInventorySnapshot",
        back_populates="beverage_item",
    )
    price_snapshots = relationship(
        "VenuePriceSnapshot",
        back_populates="beverage_item",
    )


class VenueSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "venue_snapshots"
    __table_args__ = (
        Index("ix_venue_snapshots_place_revision", "place_id", "place_revision"),
        Index("ix_venue_snapshots_status_stale", "status", "stale_after"),
        Index("ix_venue_snapshots_location", "location", postgresql_using="gist"),
        Index(
            "ix_venue_snapshots_search_document",
            "search_document",
            postgresql_using="gin",
        ),
    )

    place_id: Mapped[str] = mapped_column(String(128), nullable=False)
    place_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    place_type: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    location = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    publication_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    search_document: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    snapshot_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)
    source_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    stale_after: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    menu_snapshots = relationship(
        "VenueMenuSnapshot",
        back_populates="venue_snapshot",
        cascade="all, delete-orphan",
    )
    inventory_snapshots = relationship(
        "VenueInventorySnapshot",
        back_populates="venue_snapshot",
        cascade="all, delete-orphan",
    )
    price_snapshots = relationship(
        "VenuePriceSnapshot",
        back_populates="venue_snapshot",
        cascade="all, delete-orphan",
    )


class VenueMenuSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "venue_menu_snapshots"
    __table_args__ = (
        Index("ix_venue_menu_snapshots_place_beverage", "place_id", "beverage_item_id"),
        Index("ix_venue_menu_snapshots_place_menu", "place_id", "menu_item_id"),
    )

    venue_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("venue_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    place_id: Mapped[str] = mapped_column(String(128), nullable=False)
    menu_item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    menu_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    beverage_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("beverage_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    menu_name: Mapped[str] = mapped_column(String(255), nullable=False)
    menu_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    snapshot_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    venue_snapshot = relationship("VenueSnapshot", back_populates="menu_snapshots")
    beverage_item = relationship("BeverageItem", back_populates="menu_snapshots")


class VenueInventorySnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "venue_inventory_snapshots"
    __table_args__ = (
        Index(
            "ix_venue_inventory_snapshots_lookup",
            "place_id",
            "beverage_item_id",
            "availability_status",
        ),
        Index("ix_venue_inventory_snapshots_expires", "expires_at"),
    )

    venue_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("venue_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    place_id: Mapped[str] = mapped_column(String(128), nullable=False)
    beverage_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("beverage_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_beverage_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    inventory_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    availability_status: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    snapshot_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)

    venue_snapshot = relationship("VenueSnapshot", back_populates="inventory_snapshots")
    beverage_item = relationship("BeverageItem", back_populates="inventory_snapshots")


class VenuePriceSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "venue_price_snapshots"
    __table_args__ = (
        Index(
            "ix_venue_price_snapshots_place_beverage",
            "place_id",
            "beverage_item_id",
        ),
        Index("ix_venue_price_snapshots_valid_until", "valid_until"),
    )

    venue_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("venue_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    place_id: Mapped[str] = mapped_column(String(128), nullable=False)
    beverage_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("beverage_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    menu_item_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    price_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    price_krw: Mapped[int] = mapped_column(Integer, nullable=False)
    price_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    snapshot_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)

    venue_snapshot = relationship("VenueSnapshot", back_populates="price_snapshots")
    beverage_item = relationship("BeverageItem", back_populates="price_snapshots")


class FlavorProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "flavor_profiles"
    __table_args__ = (
        Index("ix_flavor_profiles_owner", "owner_type", "owner_id"),
    )

    owner_type: Mapped[str] = mapped_column(String(50), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    flavor_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
    )
    profile_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)
    curation_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
