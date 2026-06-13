import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.core.config import Settings
from app.grpc.gen import recommendation_pb2
from app.grpc.recommendation_service import (
    RecommendationGrpcServicer,
    _beverage_diversity_mode_from_proto,
    _beverage_flavor_direction_from_proto,
    _recommendation_to_proto,
)
from app.services.auth import StaticAuthContextResolver
from app.services.recommendations import (
    FallbackVenueDistanceProvider,
    StraightLineVenueDistanceProvider,
)


def test_recommendation_proto_does_not_accept_client_user_id() -> None:
    request = recommendation_pb2.GetBeverageRecommendationsRequest(
        category="whiskey",
        limit=10,
        budget_mode=recommendation_pb2.BUDGET_MODE_SOFT,
        exclude_beverage_ids=["11111111-1111-4111-8111-111111111111"],
        exclude_result_ids=["22222222-2222-4222-8222-222222222222"],
        diversity_mode=recommendation_pb2.BEVERAGE_DIVERSITY_MODE_DIFFERENT,
        flavor_direction=recommendation_pb2.BEVERAGE_FLAVOR_DIRECTION_SMOKIER,
    )

    assert not hasattr(request, "user_id")
    assert not hasattr(request, "external_user_id")
    assert request.category == "whiskey"
    assert request.budget_mode == recommendation_pb2.BUDGET_MODE_SOFT
    assert request.exclude_beverage_ids == [
        "11111111-1111-4111-8111-111111111111",
    ]
    assert request.exclude_result_ids == [
        "22222222-2222-4222-8222-222222222222",
    ]
    assert (
        request.diversity_mode
        == recommendation_pb2.BEVERAGE_DIVERSITY_MODE_DIFFERENT
    )
    assert (
        request.flavor_direction
        == recommendation_pb2.BEVERAGE_FLAVOR_DIRECTION_SMOKIER
    )


def test_unknown_beverage_diversity_mode_is_rejected() -> None:
    try:
        _beverage_diversity_mode_from_proto(99)
    except ValueError as exc:
        assert "unsupported beverage diversity mode" in str(exc)
    else:
        raise AssertionError("unknown diversity mode was accepted")


def test_beverage_flavor_enum_to_internal_value() -> None:
    assert (
        _beverage_flavor_direction_from_proto(
            recommendation_pb2.BEVERAGE_FLAVOR_DIRECTION_UNSPECIFIED,
        )
        is None
    )
    assert (
        _beverage_flavor_direction_from_proto(
            recommendation_pb2.BEVERAGE_FLAVOR_DIRECTION_MORE_HERBAL_BITTER,
        )
        == "more_herbal_bitter"
    )


def test_unknown_beverage_flavor_direction_is_rejected() -> None:
    try:
        _beverage_flavor_direction_from_proto(99)
    except ValueError as exc:
        assert "unsupported beverage flavor direction" in str(exc)
    else:
        raise AssertionError("unknown flavor direction was accepted")


def test_grpc_servicer_injects_venue_distance_provider() -> None:
    provider = StraightLineVenueDistanceProvider()
    servicer = RecommendationGrpcServicer(
        lambda: MagicMock(),
        StaticAuthContextResolver("user_123"),
        settings=Settings(active_scoring_config="scoring_v3"),
        venue_distance_provider=provider,
    )

    service = servicer._recommendation_service(MagicMock())  # noqa: SLF001

    assert service._venue_distance_provider is provider  # noqa: SLF001


def test_grpc_servicer_builds_http_route_distance_provider_when_enabled() -> None:
    servicer = RecommendationGrpcServicer(
        lambda: MagicMock(),
        StaticAuthContextResolver("user_123"),
        settings=Settings(
            active_scoring_config="scoring_v3",
            map_route_distance_enabled=True,
            map_service_url="https://map-service.example",
        ),
    )

    assert isinstance(  # noqa: SLF001
        servicer._venue_distance_provider,
        FallbackVenueDistanceProvider,
    )


def test_venue_recommendation_proto_does_not_accept_client_user_id() -> None:
    request = recommendation_pb2.GetVenueRecommendationsRequest(
        selected_beverage_id="11111111-1111-4111-8111-111111111111",
        lat=37.5,
        lng=127.0,
        radius_m=1500,
        limit=3,
        budget_mode=recommendation_pb2.BUDGET_MODE_SOFT,
        place_types=["store", "bar"],
    )

    assert not hasattr(request, "user_id")
    assert not hasattr(request, "external_user_id")
    assert request.selected_beverage_id
    assert request.budget_mode == recommendation_pb2.BUDGET_MODE_SOFT
    assert list(request.place_types) == ["store", "bar"]


def test_recommendation_proto_uses_concise_struct_metadata() -> None:
    recommendation = recommendation_pb2.BeverageRecommendation(
        rank=1,
        beverage_id="bev_123",
        score=0.91,
    )
    recommendation.metadata.update({"style": "bourbon"})

    assert not hasattr(recommendation, "score_breakdown_json")
    assert not hasattr(recommendation, "source_metadata_json")
    assert recommendation.metadata["style"] == "bourbon"


def test_recommendation_proto_metadata_exposes_image_url() -> None:
    recommendation = _recommendation_to_proto(
        SimpleNamespace(
            rank=1,
            result_id=uuid.uuid4(),
            target_id="bev_123",
            name_ko="테스트 위스키",
            name_en="Test Whisky",
            category="whiskey",
            final_score=0.91,
            reason_codes=["CATEGORY_MATCH"],
            explanation="fixture",
            style="bourbon",
            similarity_score=0.88,
            score_breakdown={"taste_similarity_weighted": 0.88},
            source_metadata={
                "image": {
                    "image_url": "https://example.test/whiskey.jpg",
                    "license": "Public Domain",
                },
                "image_url": "https://example.test/whiskey.jpg",
                "image_alt_text_ko": "위스키 잔 대표 이미지",
            },
        ),
    )

    assert recommendation.metadata["image_url"] == "https://example.test/whiskey.jpg"
    assert recommendation.metadata["image"]["license"] == "Public Domain"


def test_venue_recommendation_proto_uses_enums_and_optional_price() -> None:
    recommendation = recommendation_pb2.VenueRecommendation(
        rank=1,
        place_id="place_123",
        option_type=recommendation_pb2.VENUE_OPTION_TYPE_BALANCED_BEST,
        availability_status=(
            recommendation_pb2.VENUE_AVAILABILITY_STATUS_LIKELY_AVAILABLE
        ),
        freshness_status=recommendation_pb2.VENUE_FRESHNESS_STATUS_FRESH,
        score=0.88,
    )
    recommendation.metadata.update({"distance_strategy": "straight_line_mvp"})

    assert (
        recommendation.option_type
        == recommendation_pb2.VENUE_OPTION_TYPE_BALANCED_BEST
    )
    assert not recommendation.HasField("price_krw")
    recommendation.price_krw = 42000
    assert recommendation.HasField("price_krw")
    assert recommendation.metadata["distance_strategy"] == "straight_line_mvp"
