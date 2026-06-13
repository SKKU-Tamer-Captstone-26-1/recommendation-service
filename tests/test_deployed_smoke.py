import httpx
from grpc_health.v1 import health_pb2

from app.grpc.gen import auth_pb2, recommendation_pb2, survey_pb2
from app.services import deployed_smoke
from app.services.deployed_smoke import SmokeResult, run_deployed_smokes


def test_deployed_smoke_all_skips_when_env_is_missing() -> None:
    results = run_deployed_smokes(mode="all", env={})

    assert {result.name for result in results} == {
        "auth",
        "survey",
        "map",
        "map_route",
        "recommendation",
        "chat",
    }
    assert all(result.status == "skipped" for result in results)
    assert any("AUTH_SMOKE_JWKS_URL" in result.detail for result in results)


def test_deployed_smoke_rejects_unknown_mode() -> None:
    try:
        run_deployed_smokes(mode="unknown", env={})
    except ValueError as exc:
        assert "unsupported deployed smoke mode" in str(exc)
    else:
        raise AssertionError("expected unsupported mode to raise")


def test_smoke_result_serializes_for_json_output() -> None:
    result = SmokeResult(name="auth", status="passed", detail="jwks_keys=1")

    assert result.to_dict() == {
        "name": "auth",
        "status": "passed",
        "detail": "jwks_keys=1",
    }


def test_auth_smoke_can_verify_grpc_public_keys(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeChannel:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeAuthStub:
        def __init__(self, channel) -> None:
            captured["channel"] = channel

        def GetPublicKeys(self, request, *, timeout):
            captured["timeout"] = timeout
            return auth_pb2.GetPublicKeysResponse(
                keys=[auth_pb2.PublicKeyEntry(kid="kid_1", public_key_pem="pem")],
            )

    monkeypatch.setattr(
        deployed_smoke,
        "_grpc_channel",
        lambda addr, env: FakeChannel(),
    )
    monkeypatch.setattr(deployed_smoke.auth_pb2_grpc, "AuthServiceStub", FakeAuthStub)

    result = deployed_smoke.smoke_auth_metadata(
        {
            "AUTH_SMOKE_GRPC_ADDR": "authorization-service.example:443",
            "SMOKE_GRPC_TIMEOUT_SECONDS": "3",
            "AUTH_SMOKE_EXPECTED_ISSUER": "on-the-block-auth",
            "AUTH_SMOKE_EXPECTED_AUDIENCE": "recommendation-service",
        },
    )

    assert result == SmokeResult(
        name="auth",
        status="passed",
        detail=(
            "public_keys=1 expected_issuer=on-the-block-auth "
            "expected_audience=recommendation-service"
        ),
    )
    assert captured["timeout"] == 3.0


def test_auth_smoke_can_verify_grpc_token_user(monkeypatch) -> None:
    class FakeChannel:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeAuthStub:
        def __init__(self, channel) -> None:
            pass

        def GetPublicKeys(self, request, *, timeout):
            return auth_pb2.GetPublicKeysResponse(
                keys=[auth_pb2.PublicKeyEntry(kid="kid_1", public_key_pem="pem")],
            )

        def ValidateToken(self, request, *, timeout):
            return auth_pb2.ValidateTokenResponse(
                valid=True,
                user_id="usr_123",
            )

    monkeypatch.setattr(
        deployed_smoke,
        "_grpc_channel",
        lambda addr, env: FakeChannel(),
    )
    monkeypatch.setattr(deployed_smoke.auth_pb2_grpc, "AuthServiceStub", FakeAuthStub)

    result = deployed_smoke.smoke_auth_metadata(
        {
            "AUTH_SMOKE_GRPC_ADDR": "authorization-service.example:443",
            "SMOKE_AUTH_BEARER_TOKEN": "token",
            "AUTH_SMOKE_EXPECTED_USER_ID": "usr_123",
        },
    )

    assert result == SmokeResult(
        name="auth",
        status="passed",
        detail="public_keys=1 token_user_id_verified=true",
    )


def test_survey_smoke_can_verify_grpc_health(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeChannel:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeHealthStub:
        def __init__(self, channel) -> None:
            captured["channel"] = channel

        def Check(self, request, *, timeout, metadata):
            captured["service"] = request.service
            captured["timeout"] = timeout
            captured["metadata"] = metadata
            return health_pb2.HealthCheckResponse(
                status=health_pb2.HealthCheckResponse.SERVING,
            )

    monkeypatch.setattr(
        deployed_smoke,
        "_grpc_channel",
        lambda addr, env: FakeChannel(),
    )
    monkeypatch.setattr(deployed_smoke.health_pb2_grpc, "HealthStub", FakeHealthStub)

    result = deployed_smoke.smoke_survey_service(
        {
            "SURVEY_SMOKE_GRPC_ADDR": "survey-service.example:443",
            "SURVEY_SMOKE_HEALTH_SERVICE": "ontheblock.survey.v1.SurveyService",
            "SMOKE_AUTH_BEARER_TOKEN": "token",
            "SMOKE_GRPC_TIMEOUT_SECONDS": "3",
        },
    )

    assert result == SmokeResult(
        name="survey",
        status="passed",
        detail="grpc_health=SERVING sync_contract=not_verified",
    )
    assert captured["service"] == "ontheblock.survey.v1.SurveyService"
    assert captured["timeout"] == 3.0
    assert captured["metadata"] == (("authorization", "Bearer token"),)


def test_survey_smoke_can_verify_grpc_result_contract(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeChannel:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeHealthStub:
        def __init__(self, channel) -> None:
            captured["health_channel"] = channel

        def Check(self, request, *, timeout, metadata):
            return health_pb2.HealthCheckResponse(
                status=health_pb2.HealthCheckResponse.SERVING,
            )

    class FakeSurveyStub:
        def __init__(self, channel) -> None:
            captured["survey_channel"] = channel

        def GetSurveyResultByUser(self, request, *, timeout, metadata):
            captured["user_id"] = request.user_id
            result = survey_pb2.SurveyResult(
                survey_id="survey_123",
                user_id=request.user_id,
                level="expert",
                categories=["whiskey", "cognac"],
                whiskey=["bourbon_character"],
                flavor_keywords=["dried_choco"],
                budget="over_200k",
            )
            return survey_pb2.GetSurveyResultResponse(result=result)

    monkeypatch.setattr(
        deployed_smoke,
        "_grpc_channel",
        lambda addr, env: FakeChannel(),
    )
    monkeypatch.setattr(deployed_smoke.health_pb2_grpc, "HealthStub", FakeHealthStub)
    monkeypatch.setattr(
        deployed_smoke.survey_pb2_grpc, "SurveyServiceStub", FakeSurveyStub
    )

    result = deployed_smoke.smoke_survey_service(
        {
            "SURVEY_SMOKE_GRPC_ADDR": "survey-service.example:443",
            "SURVEY_SMOKE_EXTERNAL_USER_ID": "usr_123",
            "SURVEY_SMOKE_EXPECTED_USER_ID": "usr_123",
        },
    )

    assert result == SmokeResult(
        name="survey",
        status="passed",
        detail=(
            "grpc_health=SERVING survey_result_contract=verified "
            "survey_id=survey_123 categories=2 survey_user_id_verified=true"
        ),
    )
    assert captured["user_id"] == "usr_123"


def test_map_route_smoke_posts_route_distance_contract(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *, base_url, headers, timeout) -> None:
            captured["base_url"] = base_url
            captured["headers"] = headers
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, path, *, json):
            captured["path"] = path
            captured["json"] = json
            return httpx.Response(
                200,
                request=httpx.Request(
                    "POST",
                    f"https://map-service.example{path}",
                ),
                json={
                    "route_distance_m": 780.4,
                    "route_duration_seconds": 520,
                    "route_complexity": "simple",
                    "confidence": 0.88,
                },
            )

    monkeypatch.setattr(deployed_smoke.httpx, "Client", FakeClient)

    result = deployed_smoke.smoke_map_route_distance(
        {
            "MAP_ROUTE_SMOKE_BASE_URL": "https://map-service.example",
            "MAP_ROUTE_SMOKE_PLACE_ID": "place_1",
            "MAP_ROUTE_SMOKE_ORIGIN_LAT": "37.5",
            "MAP_ROUTE_SMOKE_ORIGIN_LNG": "127.0",
            "MAP_ROUTE_SMOKE_DESTINATION_LAT": "37.501",
            "MAP_ROUTE_SMOKE_DESTINATION_LNG": "127.001",
            "SMOKE_AUTH_BEARER_TOKEN": "user-access-token",
            "MAP_ROUTE_SMOKE_SERVERLESS_AUTH_TOKEN": "google-id-token",
            "MAP_ROUTE_SMOKE_EXPECT_ROUTE": "true",
            "SMOKE_HTTP_TIMEOUT_SECONDS": "3",
        },
    )

    assert result == SmokeResult(
        name="map_route",
        status="passed",
        detail=(
            "route_distance_m=780.4 route_duration_seconds=520 "
            "route_complexity=simple confidence=0.88 serverless_auth=present"
        ),
    )
    assert captured["base_url"] == "https://map-service.example"
    assert captured["timeout"] == 3.0
    assert captured["headers"] == {
        "Authorization": "Bearer user-access-token",
        "x-serverless-authorization": "Bearer google-id-token",
    }
    assert captured["path"] == "/internal/v1/recommendation/route-distance"
    assert captured["json"] == {
        "contract_version": "map_route_distance_request_v1",
        "place_id": "place_1",
        "origin": {"lat": 37.5, "lng": 127.0},
        "destination": {"lat": 37.501, "lng": 127.001},
        "requested_at": "2026-06-08T00:00:00+00:00",
    }


def test_map_route_smoke_accepts_missing_route_when_not_required(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, *, base_url, headers, timeout) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, path, *, json):
            return httpx.Response(204)

    monkeypatch.setattr(deployed_smoke.httpx, "Client", FakeClient)

    result = deployed_smoke.smoke_map_route_distance(
        {
            "MAP_ROUTE_SMOKE_BASE_URL": "https://map-service.example",
            "MAP_ROUTE_SMOKE_PLACE_ID": "place_1",
            "MAP_ROUTE_SMOKE_ORIGIN_LAT": "37.5",
            "MAP_ROUTE_SMOKE_ORIGIN_LNG": "127.0",
            "MAP_ROUTE_SMOKE_DESTINATION_LAT": "37.501",
            "MAP_ROUTE_SMOKE_DESTINATION_LNG": "127.001",
        },
    )

    assert result == SmokeResult(
        name="map_route",
        status="passed",
        detail="route_estimate=missing http_status=204",
    )


def test_map_route_smoke_rejects_missing_route_when_required(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, *, base_url, headers, timeout) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, path, *, json):
            return httpx.Response(404)

    monkeypatch.setattr(deployed_smoke.httpx, "Client", FakeClient)

    try:
        deployed_smoke.smoke_map_route_distance(
            {
                "MAP_ROUTE_SMOKE_BASE_URL": "https://map-service.example",
                "MAP_ROUTE_SMOKE_PLACE_ID": "place_1",
                "MAP_ROUTE_SMOKE_ORIGIN_LAT": "37.5",
                "MAP_ROUTE_SMOKE_ORIGIN_LNG": "127.0",
                "MAP_ROUTE_SMOKE_DESTINATION_LAT": "37.501",
                "MAP_ROUTE_SMOKE_DESTINATION_LNG": "127.001",
                "MAP_ROUTE_SMOKE_EXPECT_ROUTE": "true",
            },
        )
    except RuntimeError as exc:
        assert "expected a route estimate" in str(exc)
    else:
        raise AssertionError("expected missing route estimate to fail")


def test_recommendation_smoke_can_verify_grpc_health_only(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeChannel:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeHealthStub:
        def __init__(self, channel) -> None:
            captured["channel"] = channel

        def Check(self, request, *, timeout, metadata=()):
            captured["service"] = request.service
            captured["timeout"] = timeout
            captured["metadata"] = metadata
            return health_pb2.HealthCheckResponse(
                status=health_pb2.HealthCheckResponse.SERVING,
            )

    monkeypatch.setattr(
        deployed_smoke,
        "_recommendation_channel",
        lambda addr, env: FakeChannel(),
    )
    monkeypatch.setattr(deployed_smoke.health_pb2_grpc, "HealthStub", FakeHealthStub)

    result = deployed_smoke.smoke_recommendation_service(
        {
            "RECOMMENDATION_SMOKE_GRPC_ADDR": "recommendation-service.example:443",
            "RECOMMENDATION_SMOKE_HEALTH_ONLY": "true",
            "RECOMMENDATION_SMOKE_HEALTH_SERVICE": (
                "ontheblock.recommendation.v1.RecommendationService"
            ),
            "SMOKE_GRPC_TIMEOUT_SECONDS": "3",
        },
    )

    assert result == SmokeResult(
        name="recommendation",
        status="passed",
        detail="grpc_health=SERVING rpc_contract=not_verified",
    )
    assert captured["service"] == "ontheblock.recommendation.v1.RecommendationService"
    assert captured["timeout"] == 3.0
    assert captured["metadata"] == ()


def test_recommendation_health_smoke_can_include_serverless_auth(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeChannel:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeHealthStub:
        def __init__(self, channel) -> None:
            captured["channel"] = channel

        def Check(self, request, *, timeout, metadata=()):
            captured["metadata"] = metadata
            return health_pb2.HealthCheckResponse(
                status=health_pb2.HealthCheckResponse.SERVING,
            )

    monkeypatch.setattr(
        deployed_smoke,
        "_recommendation_channel",
        lambda addr, env: FakeChannel(),
    )
    monkeypatch.setattr(deployed_smoke.health_pb2_grpc, "HealthStub", FakeHealthStub)

    result = deployed_smoke.smoke_recommendation_service(
        {
            "RECOMMENDATION_SMOKE_GRPC_ADDR": "recommendation-service.example:443",
            "RECOMMENDATION_SMOKE_HEALTH_ONLY": "true",
            "RECOMMENDATION_SMOKE_SERVERLESS_AUTH_TOKEN": "google-id-token",
        },
    )

    assert result == SmokeResult(
        name="recommendation",
        status="passed",
        detail=(
            "grpc_health=SERVING rpc_contract=not_verified "
            "serverless_auth=present"
        ),
    )
    assert captured["metadata"] == (
        ("x-serverless-authorization", "Bearer google-id-token"),
    )


def test_recommendation_smoke_can_record_beverage_event(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeChannel:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeRecommendationStub:
        def __init__(self, channel) -> None:
            captured["channel"] = channel

        def GetProfileStatus(self, request, *, timeout, metadata):
            captured["status_metadata"] = metadata
            return recommendation_pb2.GetProfileStatusResponse(
                status=recommendation_pb2.PROFILE_STATUS_ACTIVE,
                profile_revision=1,
            )

        def GetBeverageRecommendations(self, request, *, timeout, metadata):
            captured["beverage_category"] = request.category
            return recommendation_pb2.GetBeverageRecommendationsResponse(
                request_id="11111111-1111-4111-8111-111111111111",
                profile_status=recommendation_pb2.PROFILE_STATUS_ACTIVE,
                profile_revision=1,
                recommendations=[
                    recommendation_pb2.BeverageRecommendation(
                        result_id="22222222-2222-4222-8222-222222222222",
                        beverage_id="bev_1",
                    ),
                ],
            )

        def RecordRecommendationEvent(self, request, *, timeout, metadata):
            captured["event_request_id"] = request.request_id
            captured["event_result_id"] = request.result_id
            captured["event_type"] = request.event_type
            captured["event_metadata"] = dict(request.metadata)
            return recommendation_pb2.RecordRecommendationEventResponse(
                interaction_id="33333333-3333-4333-8333-333333333333",
                duplicate=False,
            )

    monkeypatch.setattr(
        deployed_smoke,
        "_recommendation_channel",
        lambda addr, env: FakeChannel(),
    )
    monkeypatch.setattr(
        deployed_smoke.recommendation_pb2_grpc,
        "RecommendationServiceStub",
        FakeRecommendationStub,
    )

    result = deployed_smoke.smoke_recommendation_service(
        {
            "RECOMMENDATION_SMOKE_GRPC_ADDR": "recommendation-service.example:443",
            "SMOKE_AUTH_BEARER_TOKEN": "token",
            "RECOMMENDATION_SMOKE_EXPECT_ACTIVE_PROFILE": "true",
            "RECOMMENDATION_SMOKE_RUN_BEVERAGE": "true",
            "RECOMMENDATION_SMOKE_RECORD_EVENT": "true",
            "RECOMMENDATION_SMOKE_CATEGORY": "whiskey",
        },
    )

    assert result == SmokeResult(
        name="recommendation",
        status="passed",
        detail=(
            "profile_status=3 beverage_results=1 event_recorded=true "
            "event_duplicate=false"
        ),
    )
    assert captured["beverage_category"] == "whiskey"
    assert captured["event_request_id"] == "11111111-1111-4111-8111-111111111111"
    assert captured["event_result_id"] == "22222222-2222-4222-8222-222222222222"
    assert (
        captured["event_type"]
        == recommendation_pb2.RECOMMENDATION_EVENT_TYPE_IMPRESSION
    )
    assert captured["event_metadata"]["source"] == "codex_smoke"
    assert captured["status_metadata"] == (("authorization", "Bearer token"),)


def test_recommendation_smoke_validates_beverage_display_contract(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeChannel:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeRecommendationStub:
        def __init__(self, channel) -> None:
            captured["channel"] = channel

        def GetProfileStatus(self, request, *, timeout, metadata):
            return recommendation_pb2.GetProfileStatusResponse(
                status=recommendation_pb2.PROFILE_STATUS_ACTIVE,
                profile_revision=1,
            )

        def GetBeverageRecommendations(self, request, *, timeout, metadata):
            captured["flavor_direction"] = request.flavor_direction
            captured["diversity_mode"] = request.diversity_mode
            recommendation = recommendation_pb2.BeverageRecommendation(
                rank=1,
                result_id="22222222-2222-4222-8222-222222222222",
                beverage_id="33333333-3333-4333-8333-333333333333",
                name_ko="테스트 위스키",
                name_en="Test Whisky",
                category="whiskey",
                score=0.91,
                reason_codes=["CATEGORY_MATCH"],
                explanation="테스트 추천 설명입니다.",
            )
            recommendation.metadata.update(
                {
                    "image_url": "https://cdn.example.test/whisky.jpg",
                    "image_alt_text_ko": "위스키 병 이미지",
                    "image": {
                        "image_url": "https://cdn.example.test/whisky.jpg",
                        "source_url": "https://source.example.test/whisky",
                        "license": "Public Domain",
                        "cache_key": "beverage-images/v1/whisky.jpg",
                    },
                    "score_breakdown": {"taste_similarity_weighted": 0.8},
                    "source": {
                        "model_features": {
                            "budget_tradeoff": {
                                "policy_version": "beverage_budget_tradeoff_v1",
                                "status": "within_budget",
                                "display_label_ko": "예산 적합",
                                "note_ko": "카탈로그 가격대 기준입니다.",
                                "source": "catalog_price_not_live_offer",
                            },
                        },
                    },
                },
            )
            return recommendation_pb2.GetBeverageRecommendationsResponse(
                request_id="11111111-1111-4111-8111-111111111111",
                profile_status=recommendation_pb2.PROFILE_STATUS_ACTIVE,
                profile_revision=1,
                recommendations=[recommendation],
            )

    monkeypatch.setattr(
        deployed_smoke,
        "_recommendation_channel",
        lambda addr, env: FakeChannel(),
    )
    monkeypatch.setattr(
        deployed_smoke.recommendation_pb2_grpc,
        "RecommendationServiceStub",
        FakeRecommendationStub,
    )

    result = deployed_smoke.smoke_recommendation_service(
        {
            "RECOMMENDATION_SMOKE_GRPC_ADDR": "recommendation-service.example:443",
            "SMOKE_AUTH_BEARER_TOKEN": "token",
            "RECOMMENDATION_SMOKE_RUN_BEVERAGE": "true",
            "RECOMMENDATION_SMOKE_VALIDATE_BEVERAGE_CONTRACT": "true",
            "RECOMMENDATION_SMOKE_REQUIRE_IMAGE_METADATA": "true",
            "RECOMMENDATION_SMOKE_REQUIRE_BUDGET_TRADEOFF": "true",
            "RECOMMENDATION_SMOKE_EXPECT_BEVERAGE_RESULTS": "true",
            "RECOMMENDATION_SMOKE_FLAVOR_DIRECTION": "SMOKIER",
            "RECOMMENDATION_SMOKE_DIVERSITY_MODE": "ADJACENT",
        },
    )

    assert result == SmokeResult(
        name="recommendation",
        status="passed",
        detail="profile_status=3 beverage_results=1 beverage_contract=verified",
    )
    assert (
        captured["flavor_direction"]
        == recommendation_pb2.BEVERAGE_FLAVOR_DIRECTION_SMOKIER
    )
    assert (
        captured["diversity_mode"]
        == recommendation_pb2.BEVERAGE_DIVERSITY_MODE_ADJACENT
    )


def test_recommendation_smoke_rejects_beverage_contract_without_image(
    monkeypatch,
) -> None:
    class FakeChannel:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeRecommendationStub:
        def __init__(self, channel) -> None:
            pass

        def GetProfileStatus(self, request, *, timeout, metadata):
            return recommendation_pb2.GetProfileStatusResponse(
                status=recommendation_pb2.PROFILE_STATUS_ACTIVE,
                profile_revision=1,
            )

        def GetBeverageRecommendations(self, request, *, timeout, metadata):
            recommendation = recommendation_pb2.BeverageRecommendation(
                rank=1,
                result_id="22222222-2222-4222-8222-222222222222",
                beverage_id="33333333-3333-4333-8333-333333333333",
                name_ko="테스트 위스키",
                category="whiskey",
                score=0.91,
                reason_codes=["CATEGORY_MATCH"],
                explanation="테스트 추천 설명입니다.",
            )
            recommendation.metadata.update(
                {
                    "score_breakdown": {"taste_similarity_weighted": 0.8},
                    "source": {"model_features": {}},
                },
            )
            return recommendation_pb2.GetBeverageRecommendationsResponse(
                request_id="11111111-1111-4111-8111-111111111111",
                profile_status=recommendation_pb2.PROFILE_STATUS_ACTIVE,
                profile_revision=1,
                recommendations=[recommendation],
            )

    monkeypatch.setattr(
        deployed_smoke,
        "_recommendation_channel",
        lambda addr, env: FakeChannel(),
    )
    monkeypatch.setattr(
        deployed_smoke.recommendation_pb2_grpc,
        "RecommendationServiceStub",
        FakeRecommendationStub,
    )

    try:
        deployed_smoke.smoke_recommendation_service(
            {
                "RECOMMENDATION_SMOKE_GRPC_ADDR": "recommendation-service.example:443",
                "SMOKE_AUTH_BEARER_TOKEN": "token",
                "RECOMMENDATION_SMOKE_RUN_BEVERAGE": "true",
                "RECOMMENDATION_SMOKE_VALIDATE_BEVERAGE_CONTRACT": "true",
                "RECOMMENDATION_SMOKE_REQUIRE_IMAGE_METADATA": "true",
            },
        )
    except RuntimeError as exc:
        assert "image_url is missing" in str(exc)
    else:
        raise AssertionError("expected missing image metadata to fail")


def test_recommendation_smoke_validates_venue_distance_contract(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeChannel:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeRecommendationStub:
        def __init__(self, channel) -> None:
            captured["channel"] = channel

        def GetProfileStatus(self, request, *, timeout, metadata):
            return recommendation_pb2.GetProfileStatusResponse(
                status=recommendation_pb2.PROFILE_STATUS_ACTIVE,
                profile_revision=1,
            )

        def GetVenueRecommendations(self, request, *, timeout, metadata):
            captured["selected_beverage_id"] = request.selected_beverage_id
            captured["lat"] = request.lat
            captured["lng"] = request.lng
            recommendation = recommendation_pb2.VenueRecommendation(
                rank=1,
                result_id="22222222-2222-4222-8222-222222222222",
                place_id="place_fixture_1",
                name="Fixture Bottle Shop",
                place_type="liquor_shop",
                distance_m=640.2,
                score=0.82,
                reason_codes=["NEARBY_VENUE", "BALANCED_BEST"],
                explanation="거리와 재고 신뢰도를 함께 고려한 추천입니다.",
            )
            recommendation.metadata.update(
                {
                    "score_breakdown": {"distance_fit": 0.74},
                    "source": {
                        "place_revision": "place_rev_1",
                        "inventory_revision": "inventory_rev_1",
                        "price_revision": "price_rev_1",
                        "distance_m": 640.2,
                        "distance_strategy": "straight_line_mvp",
                        "distance_source": "venue_snapshot_coordinates",
                        "distance_confidence": 0.45,
                        "is_route_distance": False,
                        "distance_fallback_used": False,
                        "straight_line_distance_m": 640.2,
                    },
                },
            )
            return recommendation_pb2.GetVenueRecommendationsResponse(
                request_id="11111111-1111-4111-8111-111111111111",
                profile_status=recommendation_pb2.PROFILE_STATUS_ACTIVE,
                profile_revision=1,
                recommendations=[recommendation],
            )

    monkeypatch.setattr(
        deployed_smoke,
        "_recommendation_channel",
        lambda addr, env: FakeChannel(),
    )
    monkeypatch.setattr(
        deployed_smoke.recommendation_pb2_grpc,
        "RecommendationServiceStub",
        FakeRecommendationStub,
    )

    result = deployed_smoke.smoke_recommendation_service(
        {
            "RECOMMENDATION_SMOKE_GRPC_ADDR": "recommendation-service.example:443",
            "SMOKE_AUTH_BEARER_TOKEN": "token",
            "RECOMMENDATION_SMOKE_SELECTED_BEVERAGE_ID": "beverage_fixture_1",
            "RECOMMENDATION_SMOKE_LAT": "37.5",
            "RECOMMENDATION_SMOKE_LNG": "127.0",
            "RECOMMENDATION_SMOKE_EXPECT_VENUE_RESULTS": "true",
            "RECOMMENDATION_SMOKE_VALIDATE_VENUE_CONTRACT": "true",
        },
    )

    assert result == SmokeResult(
        name="recommendation",
        status="passed",
        detail="profile_status=3 venue_results=1 venue_contract=verified",
    )
    assert captured["selected_beverage_id"] == "beverage_fixture_1"
    assert captured["lat"] == 37.5
    assert captured["lng"] == 127.0


def test_recommendation_smoke_validates_venue_place_type_filter(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeChannel:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeRecommendationStub:
        def __init__(self, channel) -> None:
            captured["channel"] = channel

        def GetProfileStatus(self, request, *, timeout, metadata):
            return recommendation_pb2.GetProfileStatusResponse(
                status=recommendation_pb2.PROFILE_STATUS_ACTIVE,
                profile_revision=1,
            )

        def GetVenueRecommendations(self, request, *, timeout, metadata):
            captured["place_types"] = list(request.place_types)
            recommendation = recommendation_pb2.VenueRecommendation(
                rank=1,
                result_id="22222222-2222-4222-8222-222222222222",
                place_id="place_fixture_1",
                name="Fixture Liquor Shop",
                place_type="liquor_shop",
                distance_m=640.2,
                score=0.82,
                reason_codes=["NEARBY_VENUE", "BALANCED_BEST"],
                explanation="거리와 재고 신뢰도를 함께 고려한 추천입니다.",
            )
            recommendation.metadata.update(
                {
                    "score_breakdown": {"distance_fit": 0.74},
                    "source": {
                        "distance_m": 640.2,
                        "distance_strategy": "straight_line_mvp",
                        "distance_source": "venue_snapshot_coordinates",
                        "distance_confidence": 0.45,
                        "is_route_distance": False,
                        "distance_fallback_used": False,
                        "straight_line_distance_m": 640.2,
                    },
                },
            )
            return recommendation_pb2.GetVenueRecommendationsResponse(
                request_id="11111111-1111-4111-8111-111111111111",
                profile_status=recommendation_pb2.PROFILE_STATUS_ACTIVE,
                profile_revision=1,
                recommendations=[recommendation],
            )

    monkeypatch.setattr(
        deployed_smoke,
        "_recommendation_channel",
        lambda addr, env: FakeChannel(),
    )
    monkeypatch.setattr(
        deployed_smoke.recommendation_pb2_grpc,
        "RecommendationServiceStub",
        FakeRecommendationStub,
    )

    result = deployed_smoke.smoke_recommendation_service(
        {
            "RECOMMENDATION_SMOKE_GRPC_ADDR": "recommendation-service.example:443",
            "SMOKE_AUTH_BEARER_TOKEN": "token",
            "RECOMMENDATION_SMOKE_SELECTED_BEVERAGE_ID": "beverage_fixture_1",
            "RECOMMENDATION_SMOKE_VENUE_PLACE_TYPES": "store",
            "RECOMMENDATION_SMOKE_EXPECT_VENUE_RESULTS": "true",
            "RECOMMENDATION_SMOKE_VALIDATE_VENUE_CONTRACT": "true",
        },
    )

    assert result == SmokeResult(
        name="recommendation",
        status="passed",
        detail=(
            "profile_status=3 venue_results=1 venue_place_types=store "
            "venue_contract=verified venue_place_type_filter=verified"
        ),
    )
    assert captured["place_types"] == ["store"]


def test_recommendation_smoke_rejects_unexpected_venue_place_type(
    monkeypatch,
) -> None:
    class FakeChannel:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeRecommendationStub:
        def __init__(self, channel) -> None:
            pass

        def GetProfileStatus(self, request, *, timeout, metadata):
            return recommendation_pb2.GetProfileStatusResponse(
                status=recommendation_pb2.PROFILE_STATUS_ACTIVE,
                profile_revision=1,
            )

        def GetVenueRecommendations(self, request, *, timeout, metadata):
            recommendation = recommendation_pb2.VenueRecommendation(
                rank=1,
                result_id="22222222-2222-4222-8222-222222222222",
                place_id="place_fixture_1",
                name="Fixture Cocktail Bar",
                place_type="cocktail_bar",
                distance_m=640.2,
                score=0.82,
                reason_codes=["NEARBY_VENUE"],
                explanation="직선거리 기준 가까운 바입니다.",
            )
            recommendation.metadata.update(
                {
                    "score_breakdown": {"distance_fit": 0.74},
                    "source": {
                        "distance_m": 640.2,
                        "distance_strategy": "straight_line_mvp",
                        "distance_source": "venue_snapshot_coordinates",
                        "distance_confidence": 0.45,
                        "is_route_distance": False,
                        "distance_fallback_used": False,
                        "straight_line_distance_m": 640.2,
                    },
                },
            )
            return recommendation_pb2.GetVenueRecommendationsResponse(
                request_id="11111111-1111-4111-8111-111111111111",
                profile_status=recommendation_pb2.PROFILE_STATUS_ACTIVE,
                profile_revision=1,
                recommendations=[recommendation],
            )

    monkeypatch.setattr(
        deployed_smoke,
        "_recommendation_channel",
        lambda addr, env: FakeChannel(),
    )
    monkeypatch.setattr(
        deployed_smoke.recommendation_pb2_grpc,
        "RecommendationServiceStub",
        FakeRecommendationStub,
    )

    try:
        deployed_smoke.smoke_recommendation_service(
            {
                "RECOMMENDATION_SMOKE_GRPC_ADDR": (
                    "recommendation-service.example:443"
                ),
                "SMOKE_AUTH_BEARER_TOKEN": "token",
                "RECOMMENDATION_SMOKE_SELECTED_BEVERAGE_ID": "beverage_fixture_1",
                "RECOMMENDATION_SMOKE_VENUE_PLACE_TYPES": "store",
                "RECOMMENDATION_SMOKE_VALIDATE_VENUE_CONTRACT": "true",
            },
        )
    except RuntimeError as exc:
        assert "place_type is outside expected filter" in str(exc)
    else:
        raise AssertionError("expected unexpected venue place_type to fail")


def test_recommendation_smoke_requires_route_distance_when_configured(
    monkeypatch,
) -> None:
    class FakeChannel:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeRecommendationStub:
        def __init__(self, channel) -> None:
            pass

        def GetProfileStatus(self, request, *, timeout, metadata):
            return recommendation_pb2.GetProfileStatusResponse(
                status=recommendation_pb2.PROFILE_STATUS_ACTIVE,
                profile_revision=1,
            )

        def GetVenueRecommendations(self, request, *, timeout, metadata):
            recommendation = recommendation_pb2.VenueRecommendation(
                rank=1,
                result_id="22222222-2222-4222-8222-222222222222",
                place_id="place_fixture_1",
                name="Fixture Bottle Shop",
                place_type="liquor_shop",
                distance_m=780.4,
                score=0.84,
                reason_codes=["NEARBY_VENUE", "ROUTE_DISTANCE_AVAILABLE"],
                explanation="지도 경로 거리 기준으로 가까운 매장입니다.",
            )
            recommendation.metadata.update(
                {
                    "score_breakdown": {"distance_fit": 0.8},
                    "source": {
                        "place_revision": "place_rev_1",
                        "distance_m": 780.4,
                        "distance_strategy": "map_route_distance_v1",
                        "distance_source": "map_route_service",
                        "distance_confidence": 0.82,
                        "is_route_distance": True,
                        "distance_fallback_used": False,
                        "straight_line_distance_m": 640.2,
                        "route_distance_m": 780.4,
                        "route_duration_seconds": 520,
                        "route_complexity": "normal",
                    },
                },
            )
            return recommendation_pb2.GetVenueRecommendationsResponse(
                request_id="11111111-1111-4111-8111-111111111111",
                profile_status=recommendation_pb2.PROFILE_STATUS_ACTIVE,
                profile_revision=1,
                recommendations=[recommendation],
            )

    monkeypatch.setattr(
        deployed_smoke,
        "_recommendation_channel",
        lambda addr, env: FakeChannel(),
    )
    monkeypatch.setattr(
        deployed_smoke.recommendation_pb2_grpc,
        "RecommendationServiceStub",
        FakeRecommendationStub,
    )

    result = deployed_smoke.smoke_recommendation_service(
        {
            "RECOMMENDATION_SMOKE_GRPC_ADDR": "recommendation-service.example:443",
            "SMOKE_AUTH_BEARER_TOKEN": "token",
            "RECOMMENDATION_SMOKE_SELECTED_BEVERAGE_ID": "beverage_fixture_1",
            "RECOMMENDATION_SMOKE_VALIDATE_VENUE_CONTRACT": "true",
            "RECOMMENDATION_SMOKE_EXPECT_ROUTE_DISTANCE": "true",
        },
    )

    assert result == SmokeResult(
        name="recommendation",
        status="passed",
        detail=(
            "profile_status=3 venue_results=1 venue_contract=verified "
            "venue_route_results=1 venue_route_distance=verified"
        ),
    )


def test_recommendation_smoke_rejects_route_expectation_on_straight_line(
    monkeypatch,
) -> None:
    class FakeChannel:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeRecommendationStub:
        def __init__(self, channel) -> None:
            pass

        def GetProfileStatus(self, request, *, timeout, metadata):
            return recommendation_pb2.GetProfileStatusResponse(
                status=recommendation_pb2.PROFILE_STATUS_ACTIVE,
                profile_revision=1,
            )

        def GetVenueRecommendations(self, request, *, timeout, metadata):
            recommendation = recommendation_pb2.VenueRecommendation(
                rank=1,
                result_id="22222222-2222-4222-8222-222222222222",
                place_id="place_fixture_1",
                name="Fixture Bottle Shop",
                place_type="liquor_shop",
                distance_m=640.2,
                score=0.82,
                reason_codes=["NEARBY_VENUE"],
                explanation="직선거리 기준 가까운 매장입니다.",
            )
            recommendation.metadata.update(
                {
                    "score_breakdown": {"distance_fit": 0.74},
                    "source": {
                        "distance_m": 640.2,
                        "distance_strategy": "straight_line_mvp",
                        "distance_source": "venue_snapshot_coordinates",
                        "distance_confidence": 0.45,
                        "is_route_distance": False,
                        "distance_fallback_used": True,
                        "straight_line_distance_m": 640.2,
                    },
                },
            )
            return recommendation_pb2.GetVenueRecommendationsResponse(
                request_id="11111111-1111-4111-8111-111111111111",
                profile_status=recommendation_pb2.PROFILE_STATUS_ACTIVE,
                profile_revision=1,
                recommendations=[recommendation],
            )

    monkeypatch.setattr(
        deployed_smoke,
        "_recommendation_channel",
        lambda addr, env: FakeChannel(),
    )
    monkeypatch.setattr(
        deployed_smoke.recommendation_pb2_grpc,
        "RecommendationServiceStub",
        FakeRecommendationStub,
    )

    try:
        deployed_smoke.smoke_recommendation_service(
            {
                "RECOMMENDATION_SMOKE_GRPC_ADDR": (
                    "recommendation-service.example:443"
                ),
                "SMOKE_AUTH_BEARER_TOKEN": "token",
                "RECOMMENDATION_SMOKE_SELECTED_BEVERAGE_ID": "beverage_fixture_1",
                "RECOMMENDATION_SMOKE_VALIDATE_VENUE_CONTRACT": "true",
                "RECOMMENDATION_SMOKE_EXPECT_ROUTE_DISTANCE": "true",
            },
        )
    except RuntimeError as exc:
        assert "no route-distance results" in str(exc)
    else:
        raise AssertionError("expected route distance requirement to fail")


def test_recommendation_smoke_preserves_user_auth_with_serverless_auth(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeChannel:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeRecommendationStub:
        def __init__(self, channel) -> None:
            captured["channel"] = channel

        def GetProfileStatus(self, request, *, timeout, metadata):
            captured["metadata"] = metadata
            return recommendation_pb2.GetProfileStatusResponse(
                status=recommendation_pb2.PROFILE_STATUS_ACTIVE,
                profile_revision=1,
            )

    monkeypatch.setattr(
        deployed_smoke,
        "_recommendation_channel",
        lambda addr, env: FakeChannel(),
    )
    monkeypatch.setattr(
        deployed_smoke.recommendation_pb2_grpc,
        "RecommendationServiceStub",
        FakeRecommendationStub,
    )

    result = deployed_smoke.smoke_recommendation_service(
        {
            "RECOMMENDATION_SMOKE_GRPC_ADDR": "recommendation-service.example:443",
            "SMOKE_AUTH_BEARER_TOKEN": "user-access-token",
            "SMOKE_SERVERLESS_AUTH_TOKEN": "google-id-token",
        },
    )

    assert result == SmokeResult(
        name="recommendation",
        status="passed",
        detail="profile_status=3 serverless_auth=present",
    )
    assert captured["metadata"] == (
        ("authorization", "Bearer user-access-token"),
        ("x-serverless-authorization", "Bearer google-id-token"),
    )
