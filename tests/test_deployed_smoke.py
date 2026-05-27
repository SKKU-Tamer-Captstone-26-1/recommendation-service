from grpc_health.v1 import health_pb2

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
