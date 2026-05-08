import uuid

from geoalchemy2 import Geography
from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
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

    menu_items = relationship("VenueMenuItem", back_populates="beverage_item")


class Venue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "venues"
    __table_args__ = (
        Index("ix_venues_type_active", "type", "active"),
        Index("ix_venues_location", "location", postgresql_using="gist"),
        Index("ix_venues_search_document", "search_document", postgresql_using="gin"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    location = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )
    price_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_document: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    metadata_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)

    menu_items = relationship(
        "VenueMenuItem",
        back_populates="venue",
        cascade="all, delete-orphan",
    )


class VenueMenuItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "venue_menu_items"
    __table_args__ = (
        Index("ix_venue_menu_items_venue_active", "venue_id", "active"),
        Index("ix_venue_menu_items_category_active", "category", "active"),
    )

    venue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("venues.id", ondelete="CASCADE"),
        nullable=False,
    )
    beverage_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("beverage_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    price_krw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, default=dict)

    venue = relationship("Venue", back_populates="menu_items")
    beverage_item = relationship("BeverageItem", back_populates="menu_items")


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
