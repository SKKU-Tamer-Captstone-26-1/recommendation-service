from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import grpc
import httpx
from google.protobuf import struct_pb2
from grpc_health.v1 import health_pb2, health_pb2_grpc

from app.grpc.gen import (
    auth_pb2,
    auth_pb2_grpc,
    recommendation_pb2,
    recommendation_pb2_grpc,
)


class SmokeSkipped(RuntimeError):
    """Raised when a deployed smoke is intentionally skipped by configuration."""


@dataclass(frozen=True)
class SmokeResult:
    name: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
        }


Env = dict[str, str]


def run_deployed_smokes(
    *,
    mode: str,
    env: Env | None = None,
) -> tuple[SmokeResult, ...]:
    resolved_env = dict(os.environ if env is None else env)
    runners: dict[str, Callable[[Env], SmokeResult]] = {
        "auth": smoke_auth_metadata,
        "survey": smoke_survey_service,
        "map": smoke_map_service,
        "recommendation": smoke_recommendation_service,
        "chat": smoke_chat_service,
    }
    if mode == "all":
        selected: Iterable[str] = runners
    elif mode in runners:
        selected = (mode,)
    else:
        raise ValueError(f"unsupported deployed smoke mode: {mode}")

    results: list[SmokeResult] = []
    for name in selected:
        runner = runners[name]
        try:
            results.append(runner(resolved_env))
        except SmokeSkipped as exc:
            results.append(SmokeResult(name=name, status="skipped", detail=str(exc)))
    return tuple(results)


def smoke_auth_metadata(env: Env) -> SmokeResult:
    grpc_addr = env.get("AUTH_SMOKE_GRPC_ADDR")
    if grpc_addr:
        return _smoke_auth_grpc(env, grpc_addr)

    jwks_url = _required_env(env, "AUTH_SMOKE_JWKS_URL")
    timeout = _float_env(env, "SMOKE_HTTP_TIMEOUT_SECONDS", 10.0)
    response = httpx.get(jwks_url, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    keys = payload.get("keys")
    if not isinstance(keys, list) or not keys:
        raise RuntimeError("JWKS payload has no keys")
    issuer = env.get("AUTH_SMOKE_EXPECTED_ISSUER")
    audience = env.get("AUTH_SMOKE_EXPECTED_AUDIENCE")
    details = [f"jwks_keys={len(keys)}"]
    if issuer:
        details.append(f"expected_issuer={issuer}")
    if audience:
        details.append(f"expected_audience={audience}")
    return SmokeResult(name="auth", status="passed", detail=" ".join(details))


def _smoke_auth_grpc(env: Env, addr: str) -> SmokeResult:
    timeout = _float_env(env, "SMOKE_GRPC_TIMEOUT_SECONDS", 10.0)
    with _grpc_channel(addr, env) as channel:
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        response = stub.GetPublicKeys(auth_pb2.GetPublicKeysRequest(), timeout=timeout)
        if not response.keys:
            raise RuntimeError("auth GetPublicKeys returned no keys")
        details = [f"public_keys={len(response.keys)}"]
        if env.get("AUTH_SMOKE_EXPECTED_ISSUER"):
            details.append(f"expected_issuer={env['AUTH_SMOKE_EXPECTED_ISSUER']}")
        if env.get("AUTH_SMOKE_EXPECTED_AUDIENCE"):
            details.append(f"expected_audience={env['AUTH_SMOKE_EXPECTED_AUDIENCE']}")
        token = env.get("SMOKE_AUTH_BEARER_TOKEN")
        if token:
            token_response = stub.ValidateToken(
                auth_pb2.ValidateTokenRequest(access_token=token),
                timeout=timeout,
            )
            if not token_response.valid:
                raise RuntimeError(
                    "auth ValidateToken rejected smoke token: "
                    f"{token_response.reason or 'token invalid'}",
                )
            details.append("token_valid=true")
    return SmokeResult(name="auth", status="passed", detail=" ".join(details))


def smoke_survey_service(env: Env) -> SmokeResult:
    grpc_addr = env.get("SURVEY_SMOKE_GRPC_ADDR")
    if grpc_addr:
        return _smoke_survey_grpc(env, grpc_addr)

    base_url = _required_env(env, "SURVEY_SMOKE_BASE_URL")
    token = _required_env(env, "SMOKE_AUTH_BEARER_TOKEN")
    events_path = env.get(
        "SURVEY_SMOKE_EVENTS_PATH",
        "/internal/v1/recommendation/survey-events",
    )
    timeout = _float_env(env, "SMOKE_HTTP_TIMEOUT_SECONDS", 10.0)
    limit = _int_env(env, "SURVEY_SMOKE_LIMIT", 1)
    headers = _auth_headers(token)
    with httpx.Client(base_url=base_url, headers=headers, timeout=timeout) as client:
        response = client.get(events_path, params={"limit": limit})
        response.raise_for_status()
        payload = response.json()
    events = payload.get("events")
    if not isinstance(events, list):
        raise RuntimeError("survey smoke response must include events list")
    if _bool_env(env, "SURVEY_SMOKE_REQUIRE_EVENTS", False) and not events:
        raise RuntimeError("survey smoke expected at least one event")
    return SmokeResult(
        name="survey",
        status="passed",
        detail=f"events={len(events)} has_more={payload.get('has_more')}",
    )


def _smoke_survey_grpc(env: Env, grpc_addr: str) -> SmokeResult:
    timeout = _float_env(env, "SMOKE_GRPC_TIMEOUT_SECONDS", 10.0)
    token = env.get("SMOKE_AUTH_BEARER_TOKEN")
    metadata = (("authorization", f"Bearer {token}"),) if token else ()
    with _grpc_channel(grpc_addr, env) as channel:
        stub = health_pb2_grpc.HealthStub(channel)
        response = stub.Check(
            health_pb2.HealthCheckRequest(
                service=env.get("SURVEY_SMOKE_HEALTH_SERVICE", ""),
            ),
            timeout=timeout,
            metadata=metadata,
        )
    if response.status != health_pb2.HealthCheckResponse.SERVING:
        raise RuntimeError(f"survey health status is not SERVING: {response.status}")
    return SmokeResult(
        name="survey",
        status="passed",
        detail="grpc_health=SERVING sync_contract=not_verified",
    )


def smoke_map_service(env: Env) -> SmokeResult:
    base_url = _required_env(env, "MAP_SMOKE_BASE_URL")
    token = _required_env(env, "SMOKE_AUTH_BEARER_TOKEN")
    events_path = env.get(
        "MAP_SMOKE_EVENTS_PATH",
        "/internal/v1/recommendation/map-snapshot-events",
    )
    timeout = _float_env(env, "SMOKE_HTTP_TIMEOUT_SECONDS", 10.0)
    limit = _int_env(env, "MAP_SMOKE_LIMIT", 1)
    headers = _auth_headers(token)
    with httpx.Client(base_url=base_url, headers=headers, timeout=timeout) as client:
        response = client.get(events_path, params={"limit": limit})
        response.raise_for_status()
        payload = response.json()
    events = payload.get("events")
    if not isinstance(events, list):
        raise RuntimeError("map smoke response must include events list")
    if _bool_env(env, "MAP_SMOKE_REQUIRE_EVENTS", False) and not events:
        raise RuntimeError("map smoke expected at least one event")
    return SmokeResult(
        name="map",
        status="passed",
        detail=f"events={len(events)} has_more={payload.get('has_more')}",
    )


def smoke_recommendation_service(env: Env) -> SmokeResult:
    addr = _required_env(env, "RECOMMENDATION_SMOKE_GRPC_ADDR")
    if _bool_env(env, "RECOMMENDATION_SMOKE_HEALTH_ONLY", False):
        return _smoke_recommendation_grpc_health(env, addr)

    token = _required_env(env, "SMOKE_AUTH_BEARER_TOKEN")
    timeout = _float_env(env, "SMOKE_GRPC_TIMEOUT_SECONDS", 10.0)
    metadata = (("authorization", f"Bearer {token}"),)
    with _recommendation_channel(addr, env) as channel:
        stub = recommendation_pb2_grpc.RecommendationServiceStub(channel)
        beverage_response = None
        status = stub.GetProfileStatus(
            recommendation_pb2.GetProfileStatusRequest(),
            timeout=timeout,
            metadata=metadata,
        )
        details = [f"profile_status={status.status}"]
        if _bool_env(env, "RECOMMENDATION_SMOKE_EXPECT_ACTIVE_PROFILE", False):
            if status.status != recommendation_pb2.PROFILE_STATUS_ACTIVE:
                raise RuntimeError(
                    "recommendation smoke expected active profile, "
                    f"actual={status.status}",
                )

        if _bool_env(env, "RECOMMENDATION_SMOKE_RUN_BEVERAGE", False):
            beverage_response = stub.GetBeverageRecommendations(
                recommendation_pb2.GetBeverageRecommendationsRequest(
                    category=env.get("RECOMMENDATION_SMOKE_CATEGORY", ""),
                    limit=_int_env(env, "RECOMMENDATION_SMOKE_LIMIT", 3),
                    budget_mode=recommendation_pb2.BUDGET_MODE_SOFT,
                ),
                timeout=timeout,
                metadata=metadata,
            )
            details.append(
                f"beverage_results={len(beverage_response.recommendations)}",
            )
            if _bool_env(env, "RECOMMENDATION_SMOKE_RECORD_EVENT", False):
                if not beverage_response.recommendations:
                    raise RuntimeError(
                        "recommendation smoke cannot record event without "
                        "beverage recommendations",
                    )
                first = beverage_response.recommendations[0]
                event_response = stub.RecordRecommendationEvent(
                    recommendation_pb2.RecordRecommendationEventRequest(
                        request_id=beverage_response.request_id,
                        result_id=first.result_id,
                        event_type=(
                            recommendation_pb2.RECOMMENDATION_EVENT_TYPE_IMPRESSION
                        ),
                        idempotency_key=(
                            env.get("RECOMMENDATION_SMOKE_EVENT_IDEMPOTENCY_KEY")
                            or (
                                "deployed_smoke:"
                                f"{beverage_response.request_id}:"
                                f"{first.result_id}:impression"
                            )
                        ),
                        metadata=_recommendation_event_metadata(env),
                    ),
                    timeout=timeout,
                    metadata=metadata,
                )
                details.append(
                    "event_recorded=true "
                    f"event_duplicate={str(event_response.duplicate).lower()}",
                )

        selected_beverage_id = env.get("RECOMMENDATION_SMOKE_SELECTED_BEVERAGE_ID")
        if selected_beverage_id:
            response = stub.GetVenueRecommendations(
                recommendation_pb2.GetVenueRecommendationsRequest(
                    selected_beverage_id=selected_beverage_id,
                    lat=_float_env(env, "RECOMMENDATION_SMOKE_LAT", 0.0),
                    lng=_float_env(env, "RECOMMENDATION_SMOKE_LNG", 0.0),
                    radius_m=_int_env(env, "RECOMMENDATION_SMOKE_RADIUS_M", 1000),
                    limit=_int_env(env, "RECOMMENDATION_SMOKE_LIMIT", 3),
                    budget_mode=recommendation_pb2.BUDGET_MODE_SOFT,
                ),
                timeout=timeout,
                metadata=metadata,
            )
            details.append(f"venue_results={len(response.recommendations)}")

    return SmokeResult(
        name="recommendation",
        status="passed",
        detail=" ".join(details),
    )


def _recommendation_event_metadata(env: Env) -> struct_pb2.Struct:
    metadata = struct_pb2.Struct()
    metadata.update(
        {
            "client_platform": env.get(
                "RECOMMENDATION_SMOKE_CLIENT_PLATFORM",
                "codex",
            ),
            "surface": env.get("RECOMMENDATION_SMOKE_SURFACE", "deployed_smoke"),
            "source": env.get("RECOMMENDATION_SMOKE_EVENT_SOURCE", "codex_smoke"),
            "session_id_hash": env.get(
                "RECOMMENDATION_SMOKE_SESSION_ID_HASH",
                "deployed-smoke-session",
            ),
            "list_position": _int_env(env, "RECOMMENDATION_SMOKE_LIST_POSITION", 1),
            "visible_ms": _int_env(env, "RECOMMENDATION_SMOKE_VISIBLE_MS", 0),
        },
    )
    app_version = env.get("RECOMMENDATION_SMOKE_APP_VERSION")
    if app_version:
        metadata["app_version"] = app_version
    return metadata


def _smoke_recommendation_grpc_health(env: Env, addr: str) -> SmokeResult:
    timeout = _float_env(env, "SMOKE_GRPC_TIMEOUT_SECONDS", 10.0)
    with _recommendation_channel(addr, env) as channel:
        stub = health_pb2_grpc.HealthStub(channel)
        response = stub.Check(
            health_pb2.HealthCheckRequest(
                service=env.get("RECOMMENDATION_SMOKE_HEALTH_SERVICE", ""),
            ),
            timeout=timeout,
        )
    if response.status != health_pb2.HealthCheckResponse.SERVING:
        raise RuntimeError(
            f"recommendation health status is not SERVING: {response.status}",
        )
    return SmokeResult(
        name="recommendation",
        status="passed",
        detail="grpc_health=SERVING rpc_contract=not_verified",
    )


def smoke_chat_service(env: Env) -> SmokeResult:
    token = _required_env(env, "SMOKE_AUTH_BEARER_TOKEN")
    http_url = env.get("CHAT_SMOKE_HTTP_URL")
    if http_url:
        return _smoke_chat_http(env, http_url, token)

    grpc_addr = _required_env(env, "CHAT_SMOKE_GRPC_ADDR")
    timeout = _float_env(env, "SMOKE_GRPC_TIMEOUT_SECONDS", 10.0)
    with _grpc_channel(grpc_addr, env) as channel:
        stub = health_pb2_grpc.HealthStub(channel)
        response = stub.Check(
            health_pb2.HealthCheckRequest(
                service=env.get("CHAT_SMOKE_HEALTH_SERVICE", ""),
            ),
            timeout=timeout,
            metadata=(("authorization", f"Bearer {token}"),),
        )
    if response.status != health_pb2.HealthCheckResponse.SERVING:
        raise RuntimeError(f"chat health status is not SERVING: {response.status}")
    return SmokeResult(name="chat", status="passed", detail="grpc_health=SERVING")


def _smoke_chat_http(env: Env, url: str, token: str) -> SmokeResult:
    timeout = _float_env(env, "SMOKE_HTTP_TIMEOUT_SECONDS", 10.0)
    payload = _json_env(env, "CHAT_SMOKE_PAYLOAD_JSON", {"message": "recommendation"})
    with httpx.Client(headers=_auth_headers(token), timeout=timeout) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        body = response.text
    expected = env.get("CHAT_SMOKE_EXPECT_CONTAINS")
    if expected and expected not in body:
        raise RuntimeError("chat smoke response did not include expected text")
    return SmokeResult(
        name="chat",
        status="passed",
        detail=f"http_status={response.status_code}",
    )


def _recommendation_channel(addr: str, env: Env) -> grpc.Channel:
    return _grpc_channel(addr, env)


def _grpc_channel(addr: str, env: Env) -> grpc.Channel:
    use_tls = _bool_env(env, "SMOKE_GRPC_TLS", addr.endswith(":443"))
    if use_tls:
        return grpc.secure_channel(addr, grpc.ssl_channel_credentials())
    return grpc.insecure_channel(addr)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _required_env(env: Env, key: str) -> str:
    value = env.get(key)
    if not value:
        raise SmokeSkipped(f"{key} is not configured")
    return value


def _bool_env(env: Env, key: str, default: bool) -> bool:
    value = env.get(key)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _int_env(env: Env, key: str, default: int) -> int:
    value = env.get(key)
    if value is None or value == "":
        return default
    return int(value)


def _float_env(env: Env, key: str, default: float) -> float:
    value = env.get(key)
    if value is None or value == "":
        return default
    return float(value)


def _json_env(env: Env, key: str, default: Any) -> Any:
    value = env.get(key)
    if value is None or value == "":
        return default
    return json.loads(value)
