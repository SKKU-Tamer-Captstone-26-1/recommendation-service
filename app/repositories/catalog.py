import uuid
from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.catalog import (
    BeverageItem,
    FlavorProfile,
    VenueInventorySnapshot,
    VenueMenuSnapshot,
    VenuePriceSnapshot,
    VenueSnapshot,
)
from app.models.enums import FlavorProfileOwnerType, VectorOwnerType
from app.models.vector import RecommendationVector


@dataclass(frozen=True)
class BeverageVectorCandidate:
    beverage: BeverageItem
    vector: RecommendationVector
    flavor_profile: FlavorProfile | None


@dataclass(frozen=True)
class VenueSnapshotCandidate:
    venue: VenueSnapshot
    menu: VenueMenuSnapshot | None
    inventory: VenueInventorySnapshot | None
    price: VenuePriceSnapshot | None


class CatalogRepository:
    """Read access to canonical beverage catalog recommendation candidates."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_active_beverage_vector_candidates(
        self,
        *,
        vector_schema_version_id: uuid.UUID,
        category: str | None = None,
    ) -> tuple[BeverageVectorCandidate, ...]:
        flavor_join = and_(
            FlavorProfile.owner_type == FlavorProfileOwnerType.BEVERAGE_ITEM.value,
            FlavorProfile.owner_id == BeverageItem.id,
        )
        vector_join = and_(
            RecommendationVector.owner_type == VectorOwnerType.BEVERAGE_ITEM.value,
            RecommendationVector.owner_id == BeverageItem.id,
            RecommendationVector.vector_schema_version_id == vector_schema_version_id,
        )
        statement = (
            select(BeverageItem, RecommendationVector, FlavorProfile)
            .join(RecommendationVector, vector_join)
            .outerjoin(FlavorProfile, flavor_join)
            .where(BeverageItem.active.is_(True))
            .order_by(BeverageItem.category, BeverageItem.name_en, BeverageItem.id)
        )
        if category:
            statement = statement.where(BeverageItem.category == category)

        rows = self._session.execute(statement).all()
        return tuple(
            BeverageVectorCandidate(
                beverage=beverage,
                vector=vector,
                flavor_profile=flavor_profile,
            )
            for beverage, vector, flavor_profile in rows
        )

    def get_active_beverage_item(self, beverage_id: uuid.UUID) -> BeverageItem | None:
        return self._session.scalar(
            select(BeverageItem).where(
                BeverageItem.id == beverage_id,
                BeverageItem.active.is_(True),
            ),
        )

    def list_selected_beverage_venue_candidates(
        self,
        *,
        beverage_item_id: uuid.UUID,
    ) -> tuple[VenueSnapshotCandidate, ...]:
        menu_join = and_(
            VenueMenuSnapshot.venue_snapshot_id == VenueSnapshot.id,
            VenueMenuSnapshot.beverage_item_id == beverage_item_id,
        )
        inventory_join = and_(
            VenueInventorySnapshot.venue_snapshot_id == VenueSnapshot.id,
            VenueInventorySnapshot.beverage_item_id == beverage_item_id,
        )
        price_join = and_(
            VenuePriceSnapshot.venue_snapshot_id == VenueSnapshot.id,
            VenuePriceSnapshot.beverage_item_id == beverage_item_id,
        )
        statement = (
            select(
                VenueSnapshot,
                VenueMenuSnapshot,
                VenueInventorySnapshot,
                VenuePriceSnapshot,
            )
            .outerjoin(VenueMenuSnapshot, menu_join)
            .outerjoin(VenueInventorySnapshot, inventory_join)
            .outerjoin(VenuePriceSnapshot, price_join)
            .where(
                or_(
                    VenueMenuSnapshot.id.is_not(None),
                    VenueInventorySnapshot.id.is_not(None),
                    VenuePriceSnapshot.id.is_not(None),
                ),
            )
            .order_by(VenueSnapshot.place_id, VenueSnapshot.place_revision)
        )

        rows = self._session.execute(statement).all()
        return tuple(
            VenueSnapshotCandidate(
                venue=venue,
                menu=menu,
                inventory=inventory,
                price=price,
            )
            for venue, menu, inventory, price in rows
        )
