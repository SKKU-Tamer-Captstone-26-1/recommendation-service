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
