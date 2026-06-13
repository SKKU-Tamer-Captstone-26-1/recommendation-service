from __future__ import annotations

import json
import math
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import grpc
import httpx
from google.protobuf import json_format, struct_pb2
from grpc_health.v1 import health_pb2, health_pb2_grpc

from app.grpc.gen import (
    auth_pb2,
    auth_pb2_grpc,
    recommendation_pb2,
    recommendation_pb2_grpc,
    survey_pb2,
    survey_pb2_grpc,
)
from app.services.map_route_distance import (
    MAP_ROUTE_DISTANCE_REQUEST_CONTRACT,
    parse_map_route_distance_estimate,
)
from app.services.survey_sync import survey_result_to_response

VENUE_PLACE_TYPE_SMOKE_ALIASES: dict[str, tuple[str, ...]] = {
    "bar": ("bar", "cocktail_bar", "pub", "whiskey_bar", "wine_bar"),
    "bottle_shop": ("bottle_shop",),
    "cocktail_bar": ("cocktail_bar",),
    "liquor_shop": ("liquor_shop",),
    "outdoor": ("outdoor_spot", "outdoor"),
    "outdoor_spot": ("outdoor_spot",),
    "pub": ("pub", "bar"),
    "restaurant": ("restaurant",),
    "shop": ("bottle_shop", "liquor_shop", "store"),
    "store": ("bottle_shop", "liquor_shop", "store"),
    "whiskey_bar": ("whiskey_bar",),
    "wine_bar": ("wine_bar",),
}


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
        "map_route": smoke_map_route_distance,
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
            expected_user_id = env.get("AUTH_SMOKE_EXPECTED_USER_ID")
            if expected_user_id and token_response.user_id != expected_user_id:
                raise RuntimeError("auth ValidateToken returned unexpected user_id")
            if expected_user_id:
                details.append("token_user_id_verified=true")
            else:
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
        health_stub = health_pb2_grpc.HealthStub(channel)
        response = health_stub.Check(
            health_pb2.HealthCheckRequest(
                service=env.get("SURVEY_SMOKE_HEALTH_SERVICE", ""),
            ),
            timeout=timeout,
            metadata=metadata,
        )
        if response.status != health_pb2.HealthCheckResponse.SERVING:
            raise RuntimeError(
                f"survey health status is not SERVING: {response.status}",
            )

        result_detail = _smoke_survey_result_contract(
            env,
            channel,
            timeout=timeout,
            metadata=metadata,
        )
    detail = "grpc_health=SERVING"
    if result_detail:
        detail = f"{detail} {result_detail}"
    else:
        detail = f"{detail} sync_contract=not_verified"
    return SmokeResult(
        name="survey",
        status="passed",
        detail=detail,
    )


def _smoke_survey_result_contract(
    env: Env,
    channel: grpc.Channel,
    *,
    timeout: float,
    metadata: tuple[tuple[str, str], ...],
) -> str | None:
    external_user_id = env.get("SURVEY_SMOKE_EXTERNAL_USER_ID")
    survey_response_id = env.get("SURVEY_SMOKE_RESPONSE_ID")
    if not external_user_id and not survey_response_id:
        return None
    if external_user_id and survey_response_id:
        raise RuntimeError(
            "set only one of SURVEY_SMOKE_EXTERNAL_USER_ID or SURVEY_SMOKE_RESPONSE_ID",
        )

    stub = survey_pb2_grpc.SurveyServiceStub(channel)
    if external_user_id:
        response = stub.GetSurveyResultByUser(
            survey_pb2.GetSurveyResultByUserRequest(user_id=external_user_id),
            timeout=timeout,
            metadata=metadata,
        )
    else:
        response = stub.GetSurveyResult(
            survey_pb2.GetSurveyResultRequest(survey_id=survey_response_id),
            timeout=timeout,
            metadata=metadata,
        )
    mapped = survey_result_to_response(response.result)
    expected_user_id = env.get("SURVEY_SMOKE_EXPECTED_USER_ID")
    if expected_user_id and mapped.external_user_id != expected_user_id:
        raise RuntimeError("survey result returned unexpected user_id")
    user_detail = " survey_user_id_verified=true" if expected_user_id else ""
    return (
        "survey_result_contract=verified "
        f"survey_id={mapped.survey_response_id} "
        f"categories={len(mapped.answers.get('categories') or [])}"
        f"{user_detail}"
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


def smoke_map_route_distance(env: Env) -> SmokeResult:
    base_url = _first_env(env, "MAP_ROUTE_SMOKE_BASE_URL", "MAP_SMOKE_BASE_URL")
    if not base_url:
        raise SmokeSkipped(
            "MAP_ROUTE_SMOKE_BASE_URL or MAP_SMOKE_BASE_URL is not configured",
        )
    path = env.get(
        "MAP_ROUTE_SMOKE_PATH",
        "/internal/v1/recommendation/route-distance",
    )
    timeout = _float_env(env, "SMOKE_HTTP_TIMEOUT_SECONDS", 10.0)
    payload = {
        "contract_version": MAP_ROUTE_DISTANCE_REQUEST_CONTRACT,
        "place_id": _required_env(env, "MAP_ROUTE_SMOKE_PLACE_ID"),
        "origin": {
            "lat": _float_env_required(env, "MAP_ROUTE_SMOKE_ORIGIN_LAT"),
            "lng": _float_env_required(env, "MAP_ROUTE_SMOKE_ORIGIN_LNG"),
        },
        "destination": {
            "lat": _float_env_required(env, "MAP_ROUTE_SMOKE_DESTINATION_LAT"),
            "lng": _float_env_required(env, "MAP_ROUTE_SMOKE_DESTINATION_LNG"),
        },
        "requested_at": env.get(
            "MAP_ROUTE_SMOKE_REQUESTED_AT",
            "2026-06-08T00:00:00+00:00",
        ),
    }
    headers = _optional_auth_headers(env)
    headers.update(_map_route_serverless_auth_headers(env))
    with httpx.Client(base_url=base_url, headers=headers, timeout=timeout) as client:
        response = client.post(path, json=payload)
        if response.status_code in {204, 404}:
            if _bool_env(env, "MAP_ROUTE_SMOKE_EXPECT_ROUTE", False):
                raise RuntimeError("map route smoke expected a route estimate")
            return SmokeResult(
                name="map_route",
                status="passed",
                detail=f"route_estimate=missing http_status={response.status_code}",
            )
        response.raise_for_status()
        estimate = parse_map_route_distance_estimate(response.json())

    if _bool_env(env, "MAP_ROUTE_SMOKE_EXPECT_ROUTE", False) and (
        estimate.route_distance_m <= 0
    ):
        raise RuntimeError("map route smoke expected positive route distance")
    detail = (
        f"route_distance_m={estimate.route_distance_m} "
        f"route_duration_seconds={estimate.route_duration_seconds} "
        f"route_complexity={estimate.route_complexity or ''} "
        f"confidence={estimate.confidence}"
    )
    if "x-serverless-authorization" in {key.lower() for key in headers}:
        detail = f"{detail} serverless_auth=present"
    return SmokeResult(name="map_route", status="passed", detail=detail)


def smoke_recommendation_service(env: Env) -> SmokeResult:
    addr = _required_env(env, "RECOMMENDATION_SMOKE_GRPC_ADDR")
    if _bool_env(env, "RECOMMENDATION_SMOKE_HEALTH_ONLY", False):
        return _smoke_recommendation_grpc_health(env, addr)

    token = _required_env(env, "SMOKE_AUTH_BEARER_TOKEN")
    timeout = _float_env(env, "SMOKE_GRPC_TIMEOUT_SECONDS", 10.0)
    metadata = _recommendation_rpc_metadata(env, token)
    with _recommendation_channel(addr, env) as channel:
        stub = recommendation_pb2_grpc.RecommendationServiceStub(channel)
        beverage_response = None
        status = stub.GetProfileStatus(
            recommendation_pb2.GetProfileStatusRequest(),
            timeout=timeout,
            metadata=metadata,
        )
        details = [f"profile_status={status.status}"]
        if _has_serverless_auth_metadata(env):
            details.append("serverless_auth=present")
        if _bool_env(env, "RECOMMENDATION_SMOKE_EXPECT_ACTIVE_PROFILE", False):
            if status.status != recommendation_pb2.PROFILE_STATUS_ACTIVE:
                raise RuntimeError(
                    "recommendation smoke expected active profile, "
                    f"actual={status.status}",
                )

        if _bool_env(env, "RECOMMENDATION_SMOKE_RUN_BEVERAGE", False):
            beverage_response = stub.GetBeverageRecommendations(
                _beverage_recommendation_smoke_request(env),
                timeout=timeout,
                metadata=metadata,
            )
            details.append(
                f"beverage_results={len(beverage_response.recommendations)}",
            )
            if _bool_env(env, "RECOMMENDATION_SMOKE_EXPECT_BEVERAGE_RESULTS", False):
                if not beverage_response.recommendations:
                    raise RuntimeError("recommendation smoke expected beverage results")
            if _bool_env(
                env,
                "RECOMMENDATION_SMOKE_VALIDATE_BEVERAGE_CONTRACT",
                False,
            ):
                _validate_beverage_recommendation_contract(
                    beverage_response,
                    require_image_metadata=_bool_env(
                        env,
                        "RECOMMENDATION_SMOKE_REQUIRE_IMAGE_METADATA",
                        False,
                    ),
                    require_budget_tradeoff=_bool_env(
                        env,
                        "RECOMMENDATION_SMOKE_REQUIRE_BUDGET_TRADEOFF",
                        False,
                    ),
                )
                details.append("beverage_contract=verified")
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
            venue_place_types = _csv_env(
                env,
                "RECOMMENDATION_SMOKE_VENUE_PLACE_TYPES",
            )
            response = stub.GetVenueRecommendations(
                recommendation_pb2.GetVenueRecommendationsRequest(
                    selected_beverage_id=selected_beverage_id,
                    lat=_float_env(env, "RECOMMENDATION_SMOKE_LAT", 0.0),
                    lng=_float_env(env, "RECOMMENDATION_SMOKE_LNG", 0.0),
                    radius_m=_int_env(env, "RECOMMENDATION_SMOKE_RADIUS_M", 1000),
                    limit=_int_env(env, "RECOMMENDATION_SMOKE_LIMIT", 3),
                    budget_mode=recommendation_pb2.BUDGET_MODE_SOFT,
                    place_types=venue_place_types,
                ),
                timeout=timeout,
                metadata=metadata,
            )
            details.append(f"venue_results={len(response.recommendations)}")
            if venue_place_types:
                details.append(f"venue_place_types={','.join(venue_place_types)}")
            if _bool_env(env, "RECOMMENDATION_SMOKE_EXPECT_VENUE_RESULTS", False):
                if not response.recommendations:
                    raise RuntimeError("recommendation smoke expected venue results")
            if _bool_env(
                env,
                "RECOMMENDATION_SMOKE_VALIDATE_VENUE_CONTRACT",
                False,
            ):
                route_count = _validate_venue_recommendation_contract(
                    response,
                    require_route_distance=_bool_env(
                        env,
                        "RECOMMENDATION_SMOKE_EXPECT_ROUTE_DISTANCE",
                        False,
                    ),
                    allowed_place_types=_venue_place_type_expectations(
                        env,
                        request_place_types=venue_place_types,
                    ),
                )
                details.append("venue_contract=verified")
                if venue_place_types or env.get(
                    "RECOMMENDATION_SMOKE_EXPECT_VENUE_PLACE_TYPES",
                ):
                    details.append("venue_place_type_filter=verified")
                if route_count:
                    details.append(f"venue_route_results={route_count}")
                if _bool_env(
                    env,
                    "RECOMMENDATION_SMOKE_EXPECT_ROUTE_DISTANCE",
                    False,
                ):
                    details.append("venue_route_distance=verified")

    return SmokeResult(
        name="recommendation",
        status="passed",
        detail=" ".join(details),
    )


def _beverage_recommendation_smoke_request(
    env: Env,
) -> recommendation_pb2.GetBeverageRecommendationsRequest:
    return recommendation_pb2.GetBeverageRecommendationsRequest(
        category=env.get("RECOMMENDATION_SMOKE_CATEGORY", ""),
        limit=_int_env(env, "RECOMMENDATION_SMOKE_LIMIT", 3),
        budget_mode=recommendation_pb2.BUDGET_MODE_SOFT,
        diversity_mode=_beverage_diversity_mode_env(env),
        flavor_direction=_beverage_flavor_direction_env(env),
    )


def _beverage_diversity_mode_env(env: Env) -> int:
    value = env.get("RECOMMENDATION_SMOKE_DIVERSITY_MODE", "").strip().upper()
    if not value:
        return recommendation_pb2.BEVERAGE_DIVERSITY_MODE_UNSPECIFIED
    normalized = value.removeprefix("BEVERAGE_DIVERSITY_MODE_")
    modes = {
        "UNSPECIFIED": recommendation_pb2.BEVERAGE_DIVERSITY_MODE_UNSPECIFIED,
        "STANDARD": recommendation_pb2.BEVERAGE_DIVERSITY_MODE_STANDARD,
        "DIFFERENT": recommendation_pb2.BEVERAGE_DIVERSITY_MODE_DIFFERENT,
        "ADJACENT": recommendation_pb2.BEVERAGE_DIVERSITY_MODE_ADJACENT,
    }
    if normalized not in modes:
        raise ValueError(f"unsupported recommendation smoke diversity mode: {value}")
    return modes[normalized]


def _beverage_flavor_direction_env(env: Env) -> int:
    value = env.get("RECOMMENDATION_SMOKE_FLAVOR_DIRECTION", "").strip().upper()
    if not value:
        return recommendation_pb2.BEVERAGE_FLAVOR_DIRECTION_UNSPECIFIED
    normalized = value.removeprefix("BEVERAGE_FLAVOR_DIRECTION_")
    directions = {
        "UNSPECIFIED": recommendation_pb2.BEVERAGE_FLAVOR_DIRECTION_UNSPECIFIED,
        "SWEETER": recommendation_pb2.BEVERAGE_FLAVOR_DIRECTION_SWEETER,
        "LESS_SWEET": recommendation_pb2.BEVERAGE_FLAVOR_DIRECTION_LESS_SWEET,
        "SMOKIER": recommendation_pb2.BEVERAGE_FLAVOR_DIRECTION_SMOKIER,
        "LESS_SMOKY": recommendation_pb2.BEVERAGE_FLAVOR_DIRECTION_LESS_SMOKY,
        "LIGHTER": recommendation_pb2.BEVERAGE_FLAVOR_DIRECTION_LIGHTER,
        "RICHER": recommendation_pb2.BEVERAGE_FLAVOR_DIRECTION_RICHER,
        "MORE_HERBAL_BITTER": (
            recommendation_pb2.BEVERAGE_FLAVOR_DIRECTION_MORE_HERBAL_BITTER
        ),
        "BRIGHTER_FRUITY": (
            recommendation_pb2.BEVERAGE_FLAVOR_DIRECTION_BRIGHTER_FRUITY
        ),
    }
    if normalized not in directions:
        raise ValueError(
            f"unsupported recommendation smoke flavor direction: {value}",
        )
    return directions[normalized]


def _validate_beverage_recommendation_contract(
    response: recommendation_pb2.GetBeverageRecommendationsResponse,
    *,
    require_image_metadata: bool,
    require_budget_tradeoff: bool,
) -> None:
    if not response.request_id:
        raise RuntimeError("beverage recommendation response is missing request_id")
    if response.profile_status != recommendation_pb2.PROFILE_STATUS_ACTIVE:
        raise RuntimeError("beverage recommendation response profile is not active")
    if not response.recommendations:
        raise RuntimeError("beverage recommendation response has no recommendations")

    expected_rank = 1
    for item in response.recommendations:
        if item.rank != expected_rank:
            raise RuntimeError("beverage recommendation ranks are not sequential")
        expected_rank += 1
        _validate_beverage_recommendation_item(
            item,
            require_image_metadata=require_image_metadata,
            require_budget_tradeoff=require_budget_tradeoff,
        )


def _validate_beverage_recommendation_item(
    item: recommendation_pb2.BeverageRecommendation,
    *,
    require_image_metadata: bool,
    require_budget_tradeoff: bool,
) -> None:
    if not item.result_id:
        raise RuntimeError("beverage recommendation is missing result_id")
    if not item.beverage_id:
        raise RuntimeError("beverage recommendation is missing beverage_id")
    if not item.category:
        raise RuntimeError("beverage recommendation is missing category")
    if not (item.name_ko or item.name_en):
        raise RuntimeError("beverage recommendation is missing display name")
    if not math.isfinite(float(item.score)):
        raise RuntimeError("beverage recommendation score must be finite")
    if not item.reason_codes:
        raise RuntimeError("beverage recommendation is missing reason_codes")
    if not item.explanation:
        raise RuntimeError("beverage recommendation is missing explanation")

    metadata = json_format.MessageToDict(
        item.metadata,
        preserving_proto_field_name=True,
    )
    source = metadata.get("source")
    if not isinstance(source, dict):
        raise RuntimeError("beverage recommendation metadata.source is missing")
    score_breakdown = metadata.get("score_breakdown")
    if not isinstance(score_breakdown, dict):
        raise RuntimeError("beverage recommendation score_breakdown is missing")

    if require_image_metadata:
        _validate_beverage_image_metadata(metadata)
    if require_budget_tradeoff:
        _validate_beverage_budget_tradeoff(source)


def _validate_beverage_image_metadata(metadata: dict[str, Any]) -> None:
    if not isinstance(metadata.get("image_url"), str) or not metadata["image_url"]:
        raise RuntimeError("beverage recommendation image_url is missing")
    if (
        not isinstance(metadata.get("image_alt_text_ko"), str)
        or not metadata["image_alt_text_ko"]
    ):
        raise RuntimeError("beverage recommendation image_alt_text_ko is missing")
    image = metadata.get("image")
    if not isinstance(image, dict):
        raise RuntimeError("beverage recommendation image metadata is missing")
    for key in ("image_url", "source_url", "license", "cache_key"):
        if not isinstance(image.get(key), str) or not image[key]:
            raise RuntimeError(f"beverage recommendation image.{key} is missing")


def _validate_beverage_budget_tradeoff(source: dict[str, Any]) -> None:
    model_features = source.get("model_features")
    if not isinstance(model_features, dict):
        raise RuntimeError("beverage recommendation model_features is missing")
    budget_tradeoff = model_features.get("budget_tradeoff")
    if not isinstance(budget_tradeoff, dict):
        raise RuntimeError("beverage recommendation budget_tradeoff is missing")
    for key in ("policy_version", "status", "display_label_ko", "note_ko", "source"):
        if not isinstance(budget_tradeoff.get(key), str) or not budget_tradeoff[key]:
            raise RuntimeError(
                f"beverage recommendation budget_tradeoff.{key} is missing",
            )


def _validate_venue_recommendation_contract(
    response: recommendation_pb2.GetVenueRecommendationsResponse,
    *,
    require_route_distance: bool,
    allowed_place_types: tuple[str, ...] = (),
) -> int:
    if not response.request_id:
        raise RuntimeError("venue recommendation response is missing request_id")
    if response.profile_status != recommendation_pb2.PROFILE_STATUS_ACTIVE:
        raise RuntimeError("venue recommendation response profile is not active")
    if not response.recommendations:
        raise RuntimeError("venue recommendation response has no recommendations")

    route_count = 0
    expected_rank = 1
    for item in response.recommendations:
        if item.rank != expected_rank:
            raise RuntimeError("venue recommendation ranks are not sequential")
        expected_rank += 1
        if _validate_venue_recommendation_item(
            item,
            allowed_place_types=allowed_place_types,
        ):
            route_count += 1

    if require_route_distance and route_count == 0:
        raise RuntimeError(
            "venue recommendation response has no route-distance results",
        )
    return route_count


def _validate_venue_recommendation_item(
    item: recommendation_pb2.VenueRecommendation,
    *,
    allowed_place_types: tuple[str, ...] = (),
) -> bool:
    if not item.result_id:
        raise RuntimeError("venue recommendation is missing result_id")
    if not item.place_id:
        raise RuntimeError("venue recommendation is missing place_id")
    if not item.name:
        raise RuntimeError("venue recommendation is missing name")
    if not item.place_type:
        raise RuntimeError("venue recommendation is missing place_type")
    if allowed_place_types and (
        _normalize_place_type_token(item.place_type) not in set(allowed_place_types)
    ):
        raise RuntimeError(
            "venue recommendation place_type is outside expected filter: "
            f"{item.place_type}",
        )
    item_distance = _require_finite_number(
        item.distance_m,
        "venue recommendation distance_m",
    )
    if not math.isfinite(float(item.score)):
        raise RuntimeError("venue recommendation score must be finite")
    if not item.reason_codes:
        raise RuntimeError("venue recommendation is missing reason_codes")
    if not item.explanation:
        raise RuntimeError("venue recommendation is missing explanation")

    metadata = json_format.MessageToDict(
        item.metadata,
        preserving_proto_field_name=True,
    )
    score_breakdown = metadata.get("score_breakdown")
    if not isinstance(score_breakdown, dict):
        raise RuntimeError("venue recommendation score_breakdown is missing")
    source = metadata.get("source")
    if not isinstance(source, dict):
        raise RuntimeError("venue recommendation metadata.source is missing")

    source_distance = _require_finite_number(
        source.get("distance_m"),
        "venue recommendation source.distance_m",
    )
    if not math.isclose(item_distance, source_distance, abs_tol=0.01):
        raise RuntimeError("venue recommendation distance_m does not match source")
    if not isinstance(source.get("distance_strategy"), str) or not source[
        "distance_strategy"
    ]:
        raise RuntimeError(
            "venue recommendation source.distance_strategy is missing",
        )
    if not isinstance(source.get("distance_source"), str) or not source[
        "distance_source"
    ]:
        raise RuntimeError("venue recommendation source.distance_source is missing")
    confidence = _require_finite_number(
        source.get("distance_confidence"),
        "venue recommendation source.distance_confidence",
    )
    if confidence > 1.0:
        raise RuntimeError(
            "venue recommendation source.distance_confidence is outside 0..1",
        )

    is_route_distance = source.get("is_route_distance")
    if not isinstance(is_route_distance, bool):
        raise RuntimeError(
            "venue recommendation source.is_route_distance is missing",
        )
    if not isinstance(source.get("distance_fallback_used"), bool):
        raise RuntimeError(
            "venue recommendation source.distance_fallback_used is missing",
        )
    if is_route_distance:
        route_distance = _require_finite_number(
            source.get("route_distance_m"),
            "venue recommendation source.route_distance_m",
        )
        if not math.isclose(item_distance, route_distance, abs_tol=0.01):
            raise RuntimeError(
                "venue recommendation route_distance_m does not match distance_m",
            )
        route_duration = source.get("route_duration_seconds")
        if route_duration is not None:
            _require_finite_number(
                route_duration,
                "venue recommendation source.route_duration_seconds",
            )
    else:
        if source.get("route_distance_m") is not None:
            raise RuntimeError(
                "venue recommendation straight-line result has route_distance_m",
            )
        if source.get("route_duration_seconds") is not None:
            raise RuntimeError(
                "venue recommendation straight-line result has route_duration_seconds",
            )

    straight_line_distance = source.get("straight_line_distance_m")
    if straight_line_distance is not None:
        _require_finite_number(
            straight_line_distance,
            "venue recommendation source.straight_line_distance_m",
        )
    return is_route_distance


def _venue_place_type_expectations(
    env: Env,
    *,
    request_place_types: tuple[str, ...],
) -> tuple[str, ...]:
    expected = _csv_env(env, "RECOMMENDATION_SMOKE_EXPECT_VENUE_PLACE_TYPES")
    if expected:
        return _resolve_smoke_place_types(expected)
    if request_place_types:
        return _resolve_smoke_place_types(request_place_types)
    return ()


def _resolve_smoke_place_types(place_types: tuple[str, ...]) -> tuple[str, ...]:
    resolved: set[str] = set()
    for raw_place_type in place_types:
        place_type = _normalize_place_type_token(raw_place_type)
        if not place_type:
            raise ValueError("venue place type smoke value must not be blank")
        if place_type not in VENUE_PLACE_TYPE_SMOKE_ALIASES:
            raise ValueError(
                f"unsupported venue place type smoke value: {raw_place_type}",
            )
        resolved.update(VENUE_PLACE_TYPE_SMOKE_ALIASES[place_type])
    return tuple(sorted(resolved))


def _normalize_place_type_token(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _require_finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RuntimeError(f"{field_name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise RuntimeError(f"{field_name} must be a finite number")
    if number < 0:
        raise RuntimeError(f"{field_name} must be non-negative")
    return number


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
    metadata = _serverless_auth_metadata(env)
    with _recommendation_channel(addr, env) as channel:
        stub = health_pb2_grpc.HealthStub(channel)
        response = stub.Check(
            health_pb2.HealthCheckRequest(
                service=env.get("RECOMMENDATION_SMOKE_HEALTH_SERVICE", ""),
            ),
            timeout=timeout,
            metadata=metadata,
        )
    if response.status != health_pb2.HealthCheckResponse.SERVING:
        raise RuntimeError(
            f"recommendation health status is not SERVING: {response.status}",
        )
    detail = "grpc_health=SERVING rpc_contract=not_verified"
    if metadata:
        detail = f"{detail} serverless_auth=present"
    return SmokeResult(
        name="recommendation",
        status="passed",
        detail=detail,
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


def _recommendation_rpc_metadata(
    env: Env,
    user_bearer_token: str,
) -> tuple[tuple[str, str], ...]:
    return (
        ("authorization", f"Bearer {user_bearer_token}"),
        *_serverless_auth_metadata(env),
    )


def _serverless_auth_metadata(env: Env) -> tuple[tuple[str, str], ...]:
    token = (
        env.get("RECOMMENDATION_SMOKE_SERVERLESS_AUTH_TOKEN")
        or env.get("SMOKE_SERVERLESS_AUTH_TOKEN")
    )
    if not token:
        return ()
    header = env.get(
        "RECOMMENDATION_SMOKE_SERVERLESS_AUTH_HEADER",
        "x-serverless-authorization",
    ).lower()
    value = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    return ((header, value),)


def _has_serverless_auth_metadata(env: Env) -> bool:
    return bool(
        env.get("RECOMMENDATION_SMOKE_SERVERLESS_AUTH_TOKEN")
        or env.get("SMOKE_SERVERLESS_AUTH_TOKEN"),
    )


def _grpc_channel(addr: str, env: Env) -> grpc.Channel:
    use_tls = _bool_env(env, "SMOKE_GRPC_TLS", addr.endswith(":443"))
    if use_tls:
        return grpc.secure_channel(addr, grpc.ssl_channel_credentials())
    return grpc.insecure_channel(addr)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _optional_auth_headers(env: Env) -> dict[str, str]:
    token = env.get("SMOKE_AUTH_BEARER_TOKEN")
    if not token:
        return {}
    return _auth_headers(token)


def _map_route_serverless_auth_headers(env: Env) -> dict[str, str]:
    token = env.get("MAP_ROUTE_SMOKE_SERVERLESS_AUTH_TOKEN") or env.get(
        "SMOKE_SERVERLESS_AUTH_TOKEN",
    )
    if not token:
        return {}
    header = env.get(
        "MAP_ROUTE_SMOKE_SERVERLESS_AUTH_HEADER",
        "x-serverless-authorization",
    )
    value = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    return {header: value}


def _required_env(env: Env, key: str) -> str:
    value = env.get(key)
    if not value:
        raise SmokeSkipped(f"{key} is not configured")
    return value


def _first_env(env: Env, *keys: str) -> str | None:
    for key in keys:
        value = env.get(key)
        if value:
            return value
    return None


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


def _float_env_required(env: Env, key: str) -> float:
    return float(_required_env(env, key))


def _json_env(env: Env, key: str, default: Any) -> Any:
    value = env.get(key)
    if value is None or value == "":
        return default
    return json.loads(value)


def _csv_env(env: Env, key: str) -> tuple[str, ...]:
    value = env.get(key)
    if value is None or value == "":
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())
