import uuid
from dataclasses import dataclass

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.catalog import BeverageItem, FlavorProfile
from app.models.enums import FlavorProfileOwnerType, VectorOwnerType
from app.models.vector import RecommendationVector


@dataclass(frozen=True)
class BeverageVectorCandidate:
    beverage: BeverageItem
    vector: RecommendationVector
    flavor_profile: FlavorProfile | None


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
