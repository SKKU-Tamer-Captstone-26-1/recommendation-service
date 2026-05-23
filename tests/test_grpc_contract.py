from app.grpc.gen import recommendation_pb2


def test_recommendation_proto_does_not_accept_client_user_id() -> None:
    request = recommendation_pb2.GetBeverageRecommendationsRequest(
        category="whiskey",
        limit=10,
        budget_mode=recommendation_pb2.BUDGET_MODE_SOFT,
    )

    assert not hasattr(request, "user_id")
    assert not hasattr(request, "external_user_id")
    assert request.category == "whiskey"
    assert request.budget_mode == recommendation_pb2.BUDGET_MODE_SOFT


def test_venue_recommendation_proto_does_not_accept_client_user_id() -> None:
    request = recommendation_pb2.GetVenueRecommendationsRequest(
        selected_beverage_id="11111111-1111-4111-8111-111111111111",
        lat=37.5,
        lng=127.0,
        radius_m=1500,
        limit=3,
        budget_mode=recommendation_pb2.BUDGET_MODE_SOFT,
    )

    assert not hasattr(request, "user_id")
    assert not hasattr(request, "external_user_id")
    assert request.selected_beverage_id
    assert request.budget_mode == recommendation_pb2.BUDGET_MODE_SOFT


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
