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
