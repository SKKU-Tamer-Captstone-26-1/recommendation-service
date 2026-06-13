import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.models.catalog import (
    BeverageItem,
    VenueInventorySnapshot,
    VenueMenuSnapshot,
    VenuePriceSnapshot,
    VenueSnapshot,
)
from app.models.profile import TasteProfileRevision
from app.models.recommendation_event import (
    RecommendationExplanation,
    RecommendationRequest,
)
from app.models.versioning import ScoringConfig
from app.repositories.catalog import VenueSnapshotCandidate
from app.services.recommendations import (
    BeverageRecommendationService,
    FallbackVenueDistanceProvider,
    MapRouteDistanceEstimate,
    MapRouteDistanceProvider,
    StraightLineVenueDistanceProvider,
    VenueDistanceFeature,
    create_venue_distance_provider,
    rank_venue_candidates,
    score_venue_candidate,
)

NOW = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)


def test_create_venue_distance_provider_defaults_to_straight_line() -> None:
    provider = create_venue_distance_provider(
        _Settings(map_route_distance_enabled=False),
    )

    assert isinstance(provider, StraightLineVenueDistanceProvider)


def test_create_venue_distance_provider_wraps_map_route_client_with_fallback() -> None:
    provider = create_venue_distance_provider(
        _Settings(map_route_distance_enabled=True),
        route_client=_MapRouteDistanceClient(
            MapRouteDistanceEstimate(route_distance_m=780.4),
        ),
    )

    assert isinstance(provider, FallbackVenueDistanceProvider)


def test_create_venue_distance_provider_without_client_stays_straight_line() -> None:
    provider = create_venue_distance_provider(
        _Settings(map_route_distance_enabled=True),
    )

    assert isinstance(provider, StraightLineVenueDistanceProvider)


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
    assert score.source_snapshot["distance_source"] == "venue_snapshot_coordinates"
    assert score.source_snapshot["distance_confidence"] == 0.45
    assert score.source_snapshot["is_route_distance"] is False
    assert score.source_snapshot["distance_fallback_used"] is False
    assert score.source_snapshot["straight_line_distance_m"] == score.distance_m
    assert score.source_snapshot["route_distance_m"] is None
    assert score.source_snapshot["route_duration_seconds"] is None
    assert score.source_snapshot["route_complexity"] is None


def test_venue_score_accepts_route_ready_distance_provider() -> None:
    score = score_venue_candidate(
        profile=_profile(),
        selected_beverage=_beverage(),
        candidate=_candidate(place_id="place_route", price_krw=42000),
        scoring_config=_venue_scoring(),
        lat=37.5,
        lng=127.0,
        radius_m=1500,
        budget_mode="soft",
        now=NOW,
        distance_provider=_RouteDistanceProvider(),
    )

    assert score is not None
    assert score.distance_m == 900.0
    assert score.source_snapshot["distance_strategy"] == "map_route_estimate_v1"
    assert score.source_snapshot["distance_source"] == "map_service_route_api"
    assert score.source_snapshot["distance_confidence"] == 0.9
    assert score.source_snapshot["is_route_distance"] is True
    assert score.source_snapshot["distance_fallback_used"] is False
    assert score.source_snapshot["straight_line_distance_m"] == 610.0
    assert score.source_snapshot["route_distance_m"] == 900.0
    assert score.source_snapshot["route_duration_seconds"] == 720
    assert score.source_snapshot["route_complexity"] == "moderate"


def test_map_route_distance_provider_converts_client_estimate() -> None:
    client = _MapRouteDistanceClient(
        MapRouteDistanceEstimate(
            route_distance_m=780.4,
            route_duration_seconds=520,
            route_complexity="simple",
            confidence=0.88,
        ),
    )
    score = score_venue_candidate(
        profile=_profile(),
        selected_beverage=_beverage(),
        candidate=_candidate(
            place_id="place_map_route",
            lat=37.501,
            lng=127.0,
            price_krw=42000,
        ),
        scoring_config=_venue_scoring(),
        lat=37.5,
        lng=127.0,
        radius_m=1500,
        budget_mode="soft",
        now=NOW,
        distance_provider=MapRouteDistanceProvider(client),
    )

    assert score is not None
    assert score.distance_m == 780.4
    assert score.source_snapshot["distance_strategy"] == "map_route_estimate_v1"
    assert score.source_snapshot["distance_source"] == "map_service_route_api"
    assert score.source_snapshot["distance_confidence"] == 0.88
    assert score.source_snapshot["is_route_distance"] is True
    assert score.source_snapshot["distance_fallback_used"] is False
    assert score.source_snapshot["straight_line_distance_m"] is not None
    assert score.source_snapshot["route_distance_m"] == 780.4
    assert score.source_snapshot["route_duration_seconds"] == 520
    assert score.source_snapshot["route_complexity"] == "simple"
    assert client.calls == [
        {
            "place_id": "place_map_route",
            "origin_lat": 37.5,
            "origin_lng": 127.0,
            "destination_lat": 37.501,
            "destination_lng": 127.0,
            "requested_at": NOW,
        },
    ]


def test_fallback_distance_provider_uses_straight_line_when_route_missing() -> None:
    score = score_venue_candidate(
        profile=_profile(),
        selected_beverage=_beverage(),
        candidate=_candidate(
            place_id="place_route_missing",
            lat=37.501,
            lng=127.0,
            price_krw=42000,
        ),
        scoring_config=_venue_scoring(),
        lat=37.5,
        lng=127.0,
        radius_m=1500,
        budget_mode="soft",
        now=NOW,
        distance_provider=FallbackVenueDistanceProvider(
            primary=_MissingRouteDistanceProvider(),
        ),
    )

    assert score is not None
    assert score.source_snapshot["distance_strategy"] == "straight_line_mvp"
    assert score.source_snapshot["distance_source"] == "venue_snapshot_coordinates"
    assert score.source_snapshot["is_route_distance"] is False
    assert score.source_snapshot["distance_fallback_used"] is True
    assert score.source_snapshot["route_distance_m"] is None
    assert score.source_snapshot["straight_line_distance_m"] == score.distance_m


def test_map_route_distance_provider_none_uses_straight_line_fallback() -> None:
    score = score_venue_candidate(
        profile=_profile(),
        selected_beverage=_beverage(),
        candidate=_candidate(
            place_id="place_route_none",
            lat=37.501,
            lng=127.0,
            price_krw=42000,
        ),
        scoring_config=_venue_scoring(),
        lat=37.5,
        lng=127.0,
        radius_m=1500,
        budget_mode="soft",
        now=NOW,
        distance_provider=FallbackVenueDistanceProvider(
            primary=MapRouteDistanceProvider(_MapRouteDistanceClient(None)),
        ),
    )

    assert score is not None
    assert score.source_snapshot["distance_strategy"] == "straight_line_mvp"
    assert score.source_snapshot["distance_source"] == "venue_snapshot_coordinates"
    assert score.source_snapshot["is_route_distance"] is False
    assert score.source_snapshot["distance_fallback_used"] is True
    assert score.source_snapshot["route_distance_m"] is None


def test_fallback_distance_provider_uses_straight_line_when_route_invalid() -> None:
    score = score_venue_candidate(
        profile=_profile(),
        selected_beverage=_beverage(),
        candidate=_candidate(
            place_id="place_route_invalid",
            lat=37.501,
            lng=127.0,
            price_krw=42000,
        ),
        scoring_config=_venue_scoring(),
        lat=37.5,
        lng=127.0,
        radius_m=1500,
        budget_mode="soft",
        now=NOW,
        distance_provider=FallbackVenueDistanceProvider(
            primary=_InvalidRouteDistanceProvider(),
        ),
    )

    assert score is not None
    assert score.source_snapshot["distance_strategy"] == "straight_line_mvp"
    assert score.source_snapshot["distance_source"] == "venue_snapshot_coordinates"
    assert score.source_snapshot["is_route_distance"] is False
    assert score.source_snapshot["distance_fallback_used"] is True
    assert score.source_snapshot["route_distance_m"] is None
    assert score.source_snapshot["straight_line_distance_m"] == score.distance_m


def test_invalid_distance_provider_excludes_candidate_without_fallback() -> None:
    score = score_venue_candidate(
        profile=_profile(),
        selected_beverage=_beverage(),
        candidate=_candidate(place_id="place_invalid_route", price_krw=42000),
        scoring_config=_venue_scoring(),
        lat=37.5,
        lng=127.0,
        radius_m=1500,
        budget_mode="soft",
        now=NOW,
        distance_provider=_InvalidRouteDistanceProvider(),
    )

    assert score is None


def test_service_uses_injected_route_distance_provider_in_request_logs() -> None:
    beverage = _beverage()
    profile = _profile()
    candidate = _candidate(place_id="place_route", price_krw=42000)
    service, added = _venue_service_with_candidates(
        selected_beverage=beverage,
        profile=profile,
        candidates=(candidate,),
        distance_provider=_RouteDistanceProvider(),
    )

    response = service.get_venue_recommendations(
        external_user_id=profile.external_user_id,
        selected_beverage_id=str(beverage.id),
        lat=37.5,
        lng=127.0,
        radius_m=1500,
        limit=1,
        budget_mode="soft",
        now=NOW,
    )

    assert response.results[0].source_metadata["distance_strategy"] == (
        "map_route_estimate_v1"
    )
    request = _first_added(added, RecommendationRequest)
    assert request.request_context_json["distance_strategy"] == (
        "map_route_estimate_v1"
    )
    assert request.request_context_json["is_route_distance"] is True
    assert request.request_context_json["distance_sources"] == [
        "map_service_route_api",
    ]
    assert request.request_context_json["distance_result_count"] == 1
    assert request.request_context_json["route_distance_result_count"] == 1
    assert request.request_context_json["straight_line_distance_result_count"] == 0
    assert request.request_context_json["fallback_distance_result_count"] == 0
    assert request.request_context_json["unknown_distance_result_count"] == 0
    assert request.request_context_json["distance_route_coverage"] == 1.0
    assert request.request_context_json["distance_strategy_counts"] == {
        "map_route_estimate_v1": 1,
    }
    assert request.request_context_json["distance_source_counts"] == {
        "map_service_route_api": 1,
    }

    explanation = _first_added(added, RecommendationExplanation)
    assert explanation.debug_json["distance_strategy"] == "map_route_estimate_v1"
    assert explanation.debug_json["is_route_distance"] is True


def test_service_does_not_count_default_straight_line_as_fallback() -> None:
    beverage = _beverage()
    profile = _profile()
    candidate = _candidate(
        place_id="place_straight_line",
        lat=37.5002,
        lng=127.0,
        price_krw=42000,
    )
    service, added = _venue_service_with_candidates(
        selected_beverage=beverage,
        profile=profile,
        candidates=(candidate,),
        distance_provider=StraightLineVenueDistanceProvider(),
    )

    response = service.get_venue_recommendations(
        external_user_id=profile.external_user_id,
        selected_beverage_id=str(beverage.id),
        lat=37.5,
        lng=127.0,
        radius_m=1500,
        limit=1,
        budget_mode="soft",
        now=NOW,
    )

    assert response.results[0].source_metadata["distance_strategy"] == (
        "straight_line_mvp"
    )
    assert response.results[0].source_metadata["distance_fallback_used"] is False
    request = _first_added(added, RecommendationRequest)
    assert request.request_context_json["distance_strategy"] == "straight_line_mvp"
    assert request.request_context_json["is_route_distance"] is False
    assert request.request_context_json["distance_result_count"] == 1
    assert request.request_context_json["route_distance_result_count"] == 0
    assert request.request_context_json["straight_line_distance_result_count"] == 1
    assert request.request_context_json["fallback_distance_result_count"] == 0
    assert request.request_context_json["distance_route_coverage"] == 0.0


def test_service_logs_mixed_distance_strategy_on_partial_route_fallback() -> None:
    beverage = _beverage()
    profile = _profile()
    route_candidate = _candidate(
        place_id="place_route",
        lat=37.5002,
        lng=127.0,
        price_krw=43000,
    )
    fallback_candidate = _candidate(
        place_id="place_fallback",
        lat=37.5004,
        lng=127.0,
        price_krw=42000,
    )
    service, added = _venue_service_with_candidates(
        selected_beverage=beverage,
        profile=profile,
        candidates=(route_candidate, fallback_candidate),
        distance_provider=FallbackVenueDistanceProvider(
            primary=_SelectiveRouteDistanceProvider({"place_route"}),
        ),
    )

    response = service.get_venue_recommendations(
        external_user_id=profile.external_user_id,
        selected_beverage_id=str(beverage.id),
        lat=37.5,
        lng=127.0,
        radius_m=1500,
        limit=2,
        budget_mode="soft",
        now=NOW,
    )

    assert len(response.results) == 2
    strategies = {
        item.source_metadata["distance_strategy"] for item in response.results
    }
    assert strategies == {"map_route_estimate_v1", "straight_line_mvp"}

    request = _first_added(added, RecommendationRequest)
    assert request.request_context_json["distance_strategy"] == (
        "mixed_distance_strategy"
    )
    assert request.request_context_json["distance_strategies"] == [
        "map_route_estimate_v1",
        "straight_line_mvp",
    ]
    assert request.request_context_json["distance_sources"] == [
        "map_service_route_api",
        "venue_snapshot_coordinates",
    ]
    assert request.request_context_json["is_route_distance"] is True
    assert request.request_context_json["distance_result_count"] == 2
    assert request.request_context_json["route_distance_result_count"] == 1
    assert request.request_context_json["straight_line_distance_result_count"] == 1
    assert request.request_context_json["fallback_distance_result_count"] == 1
    assert request.request_context_json["unknown_distance_result_count"] == 0
    assert request.request_context_json["distance_route_coverage"] == 0.5
    assert request.request_context_json["distance_strategy_counts"] == {
        "map_route_estimate_v1": 1,
        "straight_line_mvp": 1,
    }
    assert request.request_context_json["distance_source_counts"] == {
        "map_service_route_api": 1,
        "venue_snapshot_coordinates": 1,
    }


def test_service_logs_no_distance_results_when_no_venues_rank() -> None:
    beverage = _beverage()
    profile = _profile()
    service, added = _venue_service_with_candidates(
        selected_beverage=beverage,
        profile=profile,
        candidates=(),
        distance_provider=StraightLineVenueDistanceProvider(),
    )

    response = service.get_venue_recommendations(
        external_user_id=profile.external_user_id,
        selected_beverage_id=str(beverage.id),
        lat=37.5,
        lng=127.0,
        radius_m=1500,
        limit=2,
        budget_mode="soft",
        now=NOW,
    )

    assert response.results == ()
    request = _first_added(added, RecommendationRequest)
    assert request.request_context_json["distance_strategy"] == "no_distance_results"
    assert request.request_context_json["distance_strategies"] == []
    assert request.request_context_json["distance_sources"] == []
    assert request.request_context_json["is_route_distance"] is False
    assert request.request_context_json["distance_result_count"] == 0
    assert request.request_context_json["route_distance_result_count"] == 0
    assert request.request_context_json["straight_line_distance_result_count"] == 0
    assert request.request_context_json["fallback_distance_result_count"] == 0
    assert request.request_context_json["unknown_distance_result_count"] == 0
    assert request.request_context_json["distance_route_coverage"] == 0.0
    assert request.request_context_json["distance_strategy_counts"] == {}
    assert request.request_context_json["distance_source_counts"] == {}


def test_service_filters_venue_place_types_with_aliases_in_request_logs() -> None:
    beverage = _beverage()
    profile = _profile()
    store_candidate = _candidate(
        place_id="place_store",
        place_type="liquor_shop",
        lat=37.5001,
        lng=127.0,
        price_krw=42000,
    )
    bar_candidate = _candidate(
        place_id="place_bar",
        place_type="cocktail_bar",
        lat=37.5002,
        lng=127.0,
        price_krw=44000,
    )
    outdoor_candidate = _candidate(
        place_id="place_outdoor",
        place_type="outdoor_spot",
        lat=37.5003,
        lng=127.0,
        price_krw=43000,
    )
    service, added = _venue_service_with_candidates(
        selected_beverage=beverage,
        profile=profile,
        candidates=(store_candidate, bar_candidate, outdoor_candidate),
        distance_provider=StraightLineVenueDistanceProvider(),
    )

    response = service.get_venue_recommendations(
        external_user_id=profile.external_user_id,
        selected_beverage_id=str(beverage.id),
        lat=37.5,
        lng=127.0,
        radius_m=1500,
        limit=3,
        budget_mode="soft",
        place_types=("store",),
        now=NOW,
    )

    assert [item.place_id for item in response.results] == ["place_store"]
    assert response.results[0].place_type == "liquor_shop"
    request = _first_added(added, RecommendationRequest)
    assert request.filters_json["place_types"] == ["store"]
    assert request.request_context_json["place_type_filter_policy"] == (
        "venue_snapshot_place_type_filter_v1"
    )
    assert request.request_context_json["resolved_place_types"] == [
        "bottle_shop",
        "liquor_shop",
        "store",
    ]
    assert request.request_context_json["candidate_count_before_place_type_filter"] == 3
    assert request.request_context_json["candidate_count_after_place_type_filter"] == 1


def test_service_rejects_unknown_venue_place_type_filter() -> None:
    beverage = _beverage()
    profile = _profile()
    service, _added = _venue_service_with_candidates(
        selected_beverage=beverage,
        profile=profile,
        candidates=(_candidate(place_id="place_store"),),
        distance_provider=StraightLineVenueDistanceProvider(),
    )

    with pytest.raises(ValueError, match="unsupported venue place_type"):
        service.get_venue_recommendations(
            external_user_id=profile.external_user_id,
            selected_beverage_id=str(beverage.id),
            lat=37.5,
            lng=127.0,
            radius_m=1500,
            limit=3,
            budget_mode="soft",
            place_types=("nightclub",),
            now=NOW,
        )


class _RouteDistanceProvider:
    def distance_for(
        self,
        candidate: VenueSnapshotCandidate,
        *,
        origin_lat: float,
        origin_lng: float,
        now: datetime,
    ) -> VenueDistanceFeature | None:
        return VenueDistanceFeature(
            distance_m=900.0,
            strategy="map_route_estimate_v1",
            source="map_service_route_api",
            confidence=0.9,
            is_route_distance=True,
            straight_line_distance_m=610.0,
            route_distance_m=900.0,
            route_duration_seconds=720,
            route_complexity="moderate",
        )


class _MapRouteDistanceClient:
    def __init__(self, estimate: MapRouteDistanceEstimate | None) -> None:
        self._estimate = estimate
        self.calls: list[dict[str, object]] = []

    def route_distance(
        self,
        *,
        place_id: str,
        origin_lat: float,
        origin_lng: float,
        destination_lat: float,
        destination_lng: float,
        requested_at: datetime,
    ) -> MapRouteDistanceEstimate | None:
        self.calls.append(
            {
                "place_id": place_id,
                "origin_lat": origin_lat,
                "origin_lng": origin_lng,
                "destination_lat": destination_lat,
                "destination_lng": destination_lng,
                "requested_at": requested_at,
            },
        )
        return self._estimate


class _Settings:
    def __init__(
        self,
        *,
        map_route_distance_enabled: bool,
        map_route_distance_fallback_enabled: bool = True,
    ) -> None:
        self.map_route_distance_enabled = map_route_distance_enabled
        self.map_route_distance_fallback_enabled = map_route_distance_fallback_enabled


class _MissingRouteDistanceProvider:
    def distance_for(
        self,
        candidate: VenueSnapshotCandidate,
        *,
        origin_lat: float,
        origin_lng: float,
        now: datetime,
    ) -> VenueDistanceFeature | None:
        return None


class _InvalidRouteDistanceProvider:
    def distance_for(
        self,
        candidate: VenueSnapshotCandidate,
        *,
        origin_lat: float,
        origin_lng: float,
        now: datetime,
    ) -> VenueDistanceFeature | None:
        return VenueDistanceFeature(
            distance_m=900.0,
            strategy="map_route_estimate_v1",
            source="map_service_route_api",
            confidence=1.4,
            is_route_distance=True,
            straight_line_distance_m=610.0,
            route_distance_m=None,
            route_duration_seconds=720,
            route_complexity="moderate",
        )


class _SelectiveRouteDistanceProvider:
    def __init__(self, routable_place_ids: set[str]) -> None:
        self._routable_place_ids = routable_place_ids

    def distance_for(
        self,
        candidate: VenueSnapshotCandidate,
        *,
        origin_lat: float,
        origin_lng: float,
        now: datetime,
    ) -> VenueDistanceFeature | None:
        if candidate.venue.place_id not in self._routable_place_ids:
            return None
        return VenueDistanceFeature(
            distance_m=900.0,
            strategy="map_route_estimate_v1",
            source="map_service_route_api",
            confidence=0.9,
            is_route_distance=True,
            straight_line_distance_m=50.0,
            route_distance_m=900.0,
            route_duration_seconds=720,
            route_complexity="moderate",
        )


def _venue_service_with_candidates(
    *,
    selected_beverage: BeverageItem,
    profile: TasteProfileRevision,
    candidates: tuple[VenueSnapshotCandidate, ...],
    distance_provider,
) -> tuple[BeverageRecommendationService, list[object]]:
    session = MagicMock(spec=Session)
    added: list[object] = []
    session.scalar.return_value = _venue_scoring()
    session.add.side_effect = added.append

    def flush() -> None:
        for item in added:
            if getattr(item, "id", None) is None:
                item.id = uuid.uuid4()

    session.flush.side_effect = flush
    service = BeverageRecommendationService(
        session,
        active_scoring_config="scoring_v1",
        venue_distance_provider=distance_provider,
    )
    service._profiles = _FakeProfiles(profile)  # noqa: SLF001
    service._catalog = _FakeVenueCatalog(selected_beverage, candidates)  # noqa: SLF001
    return service, added


class _FakeProfiles:
    def __init__(self, profile: TasteProfileRevision) -> None:
        self._profile = profile

    def get_active_profile_revision(self, external_user_id: str):
        return self._profile


class _FakeVenueCatalog:
    def __init__(
        self,
        selected_beverage: BeverageItem,
        candidates: tuple[VenueSnapshotCandidate, ...],
    ) -> None:
        self._selected_beverage = selected_beverage
        self._candidates = candidates

    def get_active_beverage_item(self, beverage_id: uuid.UUID) -> BeverageItem | None:
        if beverage_id == self._selected_beverage.id:
            return self._selected_beverage
        return None

    def list_selected_beverage_venue_candidates(
        self,
        *,
        beverage_item_id: uuid.UUID,
    ) -> tuple[VenueSnapshotCandidate, ...]:
        return self._candidates


def _first_added(items: list[object], model_type):
    for item in items:
        if isinstance(item, model_type):
            return item
    raise AssertionError(f"{model_type.__name__} was not added")


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
    place_type: str = "bottle_shop",
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
        place_type=place_type,
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
