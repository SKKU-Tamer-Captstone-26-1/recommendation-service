from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any, Protocol

import httpx

from app.core.config import Settings, get_settings
from app.services.recommendations import MapRouteDistanceEstimate

logger = logging.getLogger(__name__)

MAP_ROUTE_DISTANCE_REQUEST_CONTRACT = "map_route_distance_request_v1"


class ServerlessAuthTokenProvider(Protocol):
    def get_token(self) -> str | None:
        """Return a Google ID token for a private Cloud Run downstream service."""


class MetadataServerIdTokenProvider:
    """Fetch Google ID tokens from the Cloud Run metadata server."""

    def __init__(
        self,
        audience: str,
        *,
        timeout_seconds: float = 1.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._audience = audience
        self._client = client or httpx.Client(
            base_url="http://metadata.google.internal",
            timeout=timeout_seconds,
        )

    def get_token(self) -> str | None:
        try:
            response = self._client.get(
                "/computeMetadata/v1/instance/service-accounts/default/identity",
                headers={"Metadata-Flavor": "Google"},
                params={"audience": self._audience},
            )
            response.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.warning(
                "map-service serverless auth token unavailable",
                extra={
                    "structured": {
                        "event": "recommendation.map_route_serverless_token_failed",
                        "error_type": type(exc).__name__,
                    },
                },
            )
            return None

        token = response.text.strip()
        return token or None


class HttpMapRouteDistanceClient:
    """HTTP adapter for the map-service route distance contract."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.Client | None = None,
        serverless_auth_token_provider: ServerlessAuthTokenProvider | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client or httpx.Client(
            base_url=self._settings.map_service_url,
            timeout=self._settings.map_route_distance_timeout_seconds,
        )
        self._serverless_auth_token_provider = serverless_auth_token_provider

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
        headers = self._serverless_auth_headers()
        if headers is None:
            return None

        payload = {
            "contract_version": MAP_ROUTE_DISTANCE_REQUEST_CONTRACT,
            "place_id": place_id,
            "origin": {"lat": origin_lat, "lng": origin_lng},
            "destination": {"lat": destination_lat, "lng": destination_lng},
            "requested_at": requested_at.isoformat(),
        }
        try:
            response = self._client.post(
                self._settings.map_route_distance_path,
                json=payload,
                headers=headers,
            )
            if response.status_code in {204, 404}:
                return None
            response.raise_for_status()
            return parse_map_route_distance_estimate(response.json())
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as exc:
            logger.warning(
                "map-service route distance request failed",
                extra={
                    "structured": {
                        "event": "recommendation.map_route_distance_failed",
                        "place_id": place_id,
                        "error_type": type(exc).__name__,
                    },
                },
            )
            return None

    def _serverless_auth_headers(self) -> dict[str, str] | None:
        if self._serverless_auth_token_provider is None:
            return {}
        token = self._serverless_auth_token_provider.get_token()
        if not token:
            logger.warning(
                "map-service serverless auth token missing",
                extra={
                    "structured": {
                        "event": "recommendation.map_route_serverless_token_missing",
                    },
                },
            )
            return None
        return {"x-serverless-authorization": f"Bearer {token}"}


def create_http_map_route_distance_client(
    settings: Settings | None = None,
    *,
    client: httpx.Client | None = None,
    serverless_auth_token_provider: ServerlessAuthTokenProvider | None = None,
) -> HttpMapRouteDistanceClient:
    resolved_settings = settings or get_settings()
    token_provider = serverless_auth_token_provider
    if token_provider is None and resolved_settings.map_service_serverless_audience:
        token_provider = MetadataServerIdTokenProvider(
            resolved_settings.map_service_serverless_audience,
            timeout_seconds=(
                resolved_settings.map_service_serverless_token_timeout_seconds
            ),
        )
    return HttpMapRouteDistanceClient(
        resolved_settings,
        client=client,
        serverless_auth_token_provider=token_provider,
    )


def parse_map_route_distance_estimate(payload: Any) -> MapRouteDistanceEstimate:
    if not isinstance(payload, dict):
        raise ValueError("map route distance response must be an object")

    route_distance_m = _required_non_negative_float(payload, "route_distance_m")
    route_duration_seconds = _optional_non_negative_int(
        payload,
        "route_duration_seconds",
    )
    route_complexity = _optional_non_empty_string(payload, "route_complexity")
    confidence = _optional_confidence(payload, "confidence", default=0.8)

    return MapRouteDistanceEstimate(
        route_distance_m=route_distance_m,
        route_duration_seconds=route_duration_seconds,
        route_complexity=route_complexity,
        confidence=confidence,
    )


def _required_non_negative_float(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{key} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{key} must be finite and >= 0")
    return number


def _optional_non_negative_int(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    if value < 0:
        raise ValueError(f"{key} must be >= 0")
    return value


def _optional_non_empty_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_confidence(
    payload: dict[str, Any],
    key: str,
    *,
    default: float,
) -> float:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{key} must be a number")
    confidence = float(value)
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError(f"{key} must be finite and between 0 and 1")
    return confidence
