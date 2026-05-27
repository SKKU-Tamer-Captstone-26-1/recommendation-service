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
        },
    )

    assert result == SmokeResult(
        name="survey",
        status="passed",
        detail=(
            "grpc_health=SERVING survey_result_contract=verified "
            "survey_id=survey_123 categories=2"
        ),
    )
    assert captured["user_id"] == "usr_123"


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

        def Check(self, request, *, timeout):
            captured["service"] = request.service
            captured["timeout"] = timeout
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
