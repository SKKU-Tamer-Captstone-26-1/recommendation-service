"""Smoke venue recommendation logs from imported map snapshot evidence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.session import SessionLocal
from app.grpc.gen import recommendation_pb2
from app.grpc.recommendation_service import RecommendationGrpcServicer
from app.models.catalog import BeverageItem
from app.models.recommendation_event import RecommendationResult
from app.repositories.profiles import ProfileRepository
from app.services.auth import StaticAuthContextResolver
from app.services.map_snapshot_import import MapSnapshotImportService
from app.services.profile_generation import (
    ProfileGenerationService,
    SurveyProfileInput,
)

SMOKE_USER_ID = "smoke_map_snapshot_user"
SMOKE_LAT = 37.5001
SMOKE_LNG = 127.0276


def main() -> int:
    now = datetime.now(UTC)
    date_key = now.strftime("%Y%m%d")

    with SessionLocal() as session:
        beverage = _active_beverage(session)
        _ensure_profile(session, now)
        snapshot = _snapshot_payload(beverage, now, date_key)
        import_result = MapSnapshotImportService(session).import_snapshot_event(
            snapshot,
        )
        session.commit()

    servicer = RecommendationGrpcServicer(
        SessionLocal,
        StaticAuthContextResolver(SMOKE_USER_ID),
    )
    response = servicer.GetVenueRecommendations(
        recommendation_pb2.GetVenueRecommendationsRequest(
            selected_beverage_id=str(beverage.id),
            lat=SMOKE_LAT,
            lng=SMOKE_LNG,
            radius_m=1000,
            limit=3,
            budget_mode=recommendation_pb2.BUDGET_MODE_SOFT,
        ),
        _SmokeGrpcContext(),
    )
    if not response.recommendations:
        raise RuntimeError("GetVenueRecommendations returned no recommendations")

    matching = [
        item
        for item in response.recommendations
        if item.place_id == snapshot["place_id"]
    ]
    if not matching:
        returned_places = [item.place_id for item in response.recommendations]
        raise RuntimeError(
            "smoke venue was not returned; "
            f"expected={snapshot['place_id']} returned={returned_places}",
        )

    result_id = uuid.UUID(matching[0].result_id)
    with SessionLocal() as session:
        result = session.get(RecommendationResult, result_id)
        if result is None:
            raise RuntimeError(f"recommendation result not found: {result_id}")
        source = result.source_snapshot_json
        expected = {
            "place_revision": snapshot["place_revision"],
            "inventory_revision": snapshot["inventory"][0]["inventory_revision"],
            "price_revision": snapshot["prices"][0]["price_revision"],
        }
        for key, value in expected.items():
            if source.get(key) != value:
                raise RuntimeError(
                    f"source snapshot mismatch for {key}: "
                    f"expected={value} actual={source.get(key)}",
                )

    print(
        "venue recommendation smoke "
        f"request_id={response.request_id} "
        f"result_id={result_id} "
        f"place_id={snapshot['place_id']} "
        f"place_revision={snapshot['place_revision']} "
        f"inventory_revision={snapshot['inventory'][0]['inventory_revision']} "
        f"price_revision={snapshot['prices'][0]['price_revision']} "
        f"duplicate_event={import_result.duplicate_event}",
    )
    return 0


def _active_beverage(session) -> BeverageItem:
    beverage = session.scalar(
        select(BeverageItem)
        .where(BeverageItem.active.is_(True))
        .order_by(BeverageItem.category, BeverageItem.name_ko, BeverageItem.id)
        .limit(1),
    )
    if beverage is None:
        raise RuntimeError(
            "no active beverage_items row found; run "
            "`python -m app.tools.beverage_import --stage --promote-seed` first",
        )
    return beverage


def _ensure_profile(session, now: datetime) -> None:
    profile = ProfileRepository(session).get_active_profile_revision(SMOKE_USER_ID)
    if profile is not None:
        return
    ProfileGenerationService(session).generate_from_survey_input(
        SurveyProfileInput(
            survey_response_id="smoke_map_snapshot_survey",
            external_user_id=SMOKE_USER_ID,
            survey_version="survey_v1",
            response_revision=1,
            completed_at=now,
            answers={
                "categories": ["whiskey"],
                "global_keywords": ["vanilla_caramel", "oak_woody"],
                "category_traits": {"whiskey": ["vanilla_caramel", "oak_woody"]},
                "budget_range": "under_70000",
                "experience_level": "beginner",
            },
        ),
    )


def _snapshot_payload(
    beverage: BeverageItem,
    now: datetime,
    date_key: str,
) -> dict[str, object]:
    beverage_key = str(beverage.id).replace("-", "")[:12]
    place_id = f"smoke_place_{date_key}_{beverage_key}"
    return {
        "contract_version": "map_snapshot_event_v1",
        "event_id": f"smoke_map_snapshot_{date_key}_{beverage_key}",
        "event_type": "inventory.updated",
        "occurred_at": now.isoformat(),
        "place_id": place_id,
        "place_revision": f"smoke_place_rev_{date_key}",
        "venue": {
            "name": "Smoke Recommendation Bottle Shop",
            "place_type": "bottle_shop",
            "address": "Seoul, Gangnam-gu",
            "lat": SMOKE_LAT,
            "lng": SMOKE_LNG,
            "status": "active",
            "publication_status": "published",
            "stale_after": (now + timedelta(days=7)).isoformat(),
        },
        "menus": [
            {
                "menu_item_id": f"smoke_menu_{date_key}_{beverage_key}",
                "menu_revision": f"smoke_menu_rev_{date_key}",
                "beverage_item_id": str(beverage.id),
                "source_beverage_id": f"smoke_source_bev_{beverage_key}",
                "menu_name": beverage.name_ko,
                "menu_type": "bottle",
                "status": "active",
            },
        ],
        "inventory": [
            {
                "inventory_revision": f"smoke_inv_rev_{date_key}",
                "beverage_item_id": str(beverage.id),
                "source_beverage_id": f"smoke_source_bev_{beverage_key}",
                "availability_status": "available",
                "confidence": 0.95,
                "last_seen_at": now.isoformat(),
                "expires_at": (now + timedelta(days=3)).isoformat(),
            },
        ],
        "prices": [
            {
                "price_revision": f"smoke_price_rev_{date_key}",
                "beverage_item_id": str(beverage.id),
                "menu_item_id": f"smoke_menu_{date_key}_{beverage_key}",
                "price_krw": 42000,
                "price_type": "retail",
                "confidence": 0.9,
                "valid_from": now.isoformat(),
                "valid_until": (now + timedelta(days=7)).isoformat(),
            },
        ],
    }


class _SmokeGrpcContext:
    def invocation_metadata(self) -> tuple[object, ...]:
        return ()

    def abort(self, code, details):
        raise RuntimeError(f"{code.name}: {details}")


if __name__ == "__main__":
    raise SystemExit(main())
