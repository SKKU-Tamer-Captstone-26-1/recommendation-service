import uuid
from datetime import UTC, datetime, timedelta

from app.models.catalog import (
    BeverageItem,
    VenueInventorySnapshot,
    VenueMenuSnapshot,
    VenuePriceSnapshot,
    VenueSnapshot,
)
from app.models.profile import TasteProfileRevision
from app.models.versioning import ScoringConfig
from app.repositories.catalog import VenueSnapshotCandidate
from app.services.recommendations import (
    rank_venue_candidates,
    score_venue_candidate,
)

NOW = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)


def test_rank_venue_candidates_returns_distinct_tradeoff_options() -> None:
    beverage = _beverage()
    profile = _profile()
    scoring = _venue_scoring()
    candidates = (
        _candidate(
            place_id="place_near",
            lat=37.5005,
            lng=127.0,
            price_krw=60000,
            confidence=0.8,
            inventory_confidence=0.75,
        ),
        _candidate(
            place_id="place_price",
            lat=37.506,
            lng=127.0,
            price_krw=39000,
            confidence=0.8,
            inventory_confidence=0.7,
        ),
        _candidate(
            place_id="place_balanced",
            lat=37.501,
            lng=127.001,
            price_krw=43000,
            confidence=0.95,
            inventory_confidence=0.95,
        ),
    )

    ranked = rank_venue_candidates(
        profile=profile,
        selected_beverage=beverage,
        candidates=candidates,
        scoring_config=scoring,
        lat=37.5,
        lng=127.0,
        radius_m=1500,
        limit=3,
        budget_mode="soft",
        now=NOW,
    )

    assert len(ranked) == 3
    assert len({item.candidate.venue.place_id for item in ranked}) == 3
    assert {item.option_type for item in ranked} == {
        "nearest_reasonable",
        "best_price",
        "balanced_best",
    }
    assert ranked[0].candidate.venue.place_id == "place_near"
    assert "NEAREST_REASONABLE" in ranked[0].score.reason_codes
    assert all(
        "SELECTED_BEVERAGE_AVAILABLE" in item.score.reason_codes for item in ranked
    )


def test_venue_candidate_excludes_closed_and_expired_snapshots() -> None:
    beverage = _beverage()
    profile = _profile()
    scoring = _venue_scoring()

    closed = _candidate(
        place_id="place_closed",
        status="closed",
        price_krw=40000,
    )
    expired_inventory = _candidate(
        place_id="place_expired",
        price_krw=40000,
        last_seen_at=NOW - timedelta(days=31),
    )

    assert (
        score_venue_candidate(
            profile=profile,
            selected_beverage=beverage,
            candidate=closed,
            scoring_config=scoring,
            lat=37.5,
            lng=127.0,
            radius_m=1500,
            budget_mode="soft",
            now=NOW,
        )
        is None
    )
    assert (
        score_venue_candidate(
            profile=profile,
            selected_beverage=beverage,
            candidate=expired_inventory,
            scoring_config=scoring,
            lat=37.5,
            lng=127.0,
            radius_m=1500,
            budget_mode="soft",
            now=NOW,
        )
        is None
    )


def test_strict_budget_requires_valid_price_snapshot() -> None:
    score = score_venue_candidate(
        profile=_profile(),
        selected_beverage=_beverage(),
        candidate=_candidate(place_id="place_no_price", price_krw=None),
        scoring_config=_venue_scoring(),
        lat=37.5,
        lng=127.0,
        radius_m=1500,
        budget_mode="strict",
        now=NOW,
    )

    assert score is None


def test_venue_score_preserves_snapshot_revision_metadata() -> None:
    score = score_venue_candidate(
        profile=_profile(),
        selected_beverage=_beverage(),
        candidate=_candidate(place_id="place_meta", price_krw=42000),
        scoring_config=_venue_scoring(),
        lat=37.5,
        lng=127.0,
        radius_m=1500,
        budget_mode="soft",
        now=NOW,
    )

    assert score is not None
    assert score.source_snapshot["place_revision"] == "place_rev_place_meta"
    assert score.source_snapshot["menu_revision"] == "menu_rev_place_meta"
    assert score.source_snapshot["inventory_revision"] == "inv_rev_place_meta"
    assert score.source_snapshot["price_revision"] == "price_rev_place_meta"
    assert score.source_snapshot["distance_strategy"] == "straight_line_mvp"


def _beverage() -> BeverageItem:
    return BeverageItem(
        id=uuid.uuid4(),
        category="whiskey",
        name_ko="테스트 위스키",
        name_en="Test Whiskey",
        active=True,
        metadata_json={},
    )


def _profile() -> TasteProfileRevision:
    return TasteProfileRevision(
        id=uuid.uuid4(),
        external_user_id="usr_123",
        profile_revision=1,
        survey_response_id="surv_resp_123",
        survey_version="survey_v1",
        survey_response_revision=1,
        mapper_version_id=uuid.uuid4(),
        vector_schema_version_id=uuid.uuid4(),
        taste_vector=[0.0] * 16,
        taste_vector_json={},
        confidence_json={},
        preferred_categories=["whiskey"],
        preferred_keywords=[],
        budget_range="30000_50000",
        experience_level="beginner",
        status="active",
        generation_metadata_json={},
    )


def _venue_scoring() -> ScoringConfig:
    return ScoringConfig(
        id=uuid.uuid4(),
        name="default_scoring",
        version="scoring_v1",
        target_type="venue",
        category="all",
        weights_json={
            "taste_similarity_weighted": 0.35,
            "distance_fit": 0.20,
            "budget_fit": 0.10,
            "availability_confidence": 0.15,
            "price_confidence": 0.10,
            "freshness_adjustment": 0.10,
        },
        reason_code_rules_json={},
        status="active",
    )


def _candidate(
    *,
    place_id: str,
    lat: float = 37.5,
    lng: float = 127.0,
    status: str = "active",
    price_krw: int | None = 45000,
    confidence: float = 0.8,
    inventory_confidence: float = 0.8,
    last_seen_at: datetime = NOW - timedelta(days=1),
) -> VenueSnapshotCandidate:
    venue_id = uuid.uuid4()
    beverage_id = uuid.uuid4()
    venue = VenueSnapshot(
        id=venue_id,
        place_id=place_id,
        place_revision=f"place_rev_{place_id}",
        name=f"Venue {place_id}",
        place_type="bottle_shop",
        address="Seoul",
        status=status,
        publication_status="published",
        snapshot_json={"lat": lat, "lng": lng},
        synced_at=NOW,
    )
    menu = VenueMenuSnapshot(
        id=uuid.uuid4(),
        venue_snapshot_id=venue_id,
        place_id=place_id,
        menu_item_id=f"menu_{place_id}",
        menu_revision=f"menu_rev_{place_id}",
        beverage_item_id=beverage_id,
        menu_name="Test Pour",
        status="active",
        snapshot_json={},
        synced_at=NOW,
    )
    inventory = VenueInventorySnapshot(
        id=uuid.uuid4(),
        venue_snapshot_id=venue_id,
        place_id=place_id,
        beverage_item_id=beverage_id,
        inventory_revision=f"inv_rev_{place_id}",
        availability_status="available",
        confidence=inventory_confidence,
        last_seen_at=last_seen_at,
        snapshot_json={},
        synced_at=NOW,
    )
    price = (
        VenuePriceSnapshot(
            id=uuid.uuid4(),
            venue_snapshot_id=venue_id,
            place_id=place_id,
            beverage_item_id=beverage_id,
            menu_item_id=f"menu_{place_id}",
            price_revision=f"price_rev_{place_id}",
            price_krw=price_krw,
            price_type="menu",
            confidence=confidence,
            valid_until=NOW + timedelta(days=2),
            snapshot_json={},
            synced_at=NOW,
        )
        if price_krw is not None
        else None
    )
    return VenueSnapshotCandidate(
        venue=venue,
        menu=menu,
        inventory=inventory,
        price=price,
    )
