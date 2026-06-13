import json
from datetime import UTC, datetime

import httpx

from app.core.config import Settings
from app.services.map_route_distance import (
    HttpMapRouteDistanceClient,
    MetadataServerIdTokenProvider,
    parse_map_route_distance_estimate,
)

NOW = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)


def test_http_map_route_distance_client_posts_v1_request_and_parses_estimate() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "route_distance_m": 780.4,
                "route_duration_seconds": 520,
                "route_complexity": "simple",
                "confidence": 0.88,
            },
        )

    route_client = HttpMapRouteDistanceClient(
        Settings(map_service_url="https://map-service.example"),
        client=httpx.Client(
            base_url="https://map-service.example",
            transport=httpx.MockTransport(handler),
        ),
        serverless_auth_token_provider=_TokenProvider("google-id-token"),
    )

    estimate = route_client.route_distance(
        place_id="place_1",
        origin_lat=37.5,
        origin_lng=127.0,
        destination_lat=37.501,
        destination_lng=127.001,
        requested_at=NOW,
    )

    assert estimate is not None
    assert estimate.route_distance_m == 780.4
    assert estimate.route_duration_seconds == 520
    assert estimate.route_complexity == "simple"
    assert estimate.confidence == 0.88
    assert requests[0].url.path == "/internal/v1/recommendation/route-distance"
    assert requests[0].headers["x-serverless-authorization"] == (
        "Bearer google-id-token"
    )
    body = json.loads(requests[0].content)
    assert body == {
        "contract_version": "map_route_distance_request_v1",
        "place_id": "place_1",
        "origin": {"lat": 37.5, "lng": 127.0},
        "destination": {"lat": 37.501, "lng": 127.001},
        "requested_at": "2026-06-08T12:00:00+00:00",
    }


def test_http_map_route_distance_client_returns_none_for_no_route() -> None:
    route_client = HttpMapRouteDistanceClient(
        Settings(map_service_url="https://map-service.example"),
        client=httpx.Client(
            base_url="https://map-service.example",
            transport=httpx.MockTransport(lambda request: httpx.Response(204)),
        ),
    )

    assert (
        route_client.route_distance(
            place_id="place_1",
            origin_lat=37.5,
            origin_lng=127.0,
            destination_lat=37.501,
            destination_lng=127.001,
            requested_at=NOW,
        )
        is None
    )


def test_http_map_route_distance_client_returns_none_for_invalid_payload() -> None:
    route_client = HttpMapRouteDistanceClient(
        Settings(map_service_url="https://map-service.example"),
        client=httpx.Client(
            base_url="https://map-service.example",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"route_distance_m": -1}),
            ),
        ),
    )

    assert (
        route_client.route_distance(
            place_id="place_1",
            origin_lat=37.5,
            origin_lng=127.0,
            destination_lat=37.501,
            destination_lng=127.001,
            requested_at=NOW,
        )
        is None
    )


def test_http_map_route_distance_client_returns_none_for_request_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    route_client = HttpMapRouteDistanceClient(
        Settings(map_service_url="https://map-service.example"),
        client=httpx.Client(
            base_url="https://map-service.example",
            transport=httpx.MockTransport(handler),
        ),
    )

    assert (
        route_client.route_distance(
            place_id="place_1",
            origin_lat=37.5,
            origin_lng=127.0,
            destination_lat=37.501,
            destination_lng=127.001,
            requested_at=NOW,
        )
        is None
    )


def test_http_map_route_client_skips_request_without_serverless_token() -> None:
    requests: list[httpx.Request] = []

    route_client = HttpMapRouteDistanceClient(
        Settings(map_service_url="https://map-service.example"),
        client=httpx.Client(
            base_url="https://map-service.example",
            transport=httpx.MockTransport(
                lambda request: requests.append(request) or httpx.Response(200),
            ),
        ),
        serverless_auth_token_provider=_TokenProvider(None),
    )

    assert (
        route_client.route_distance(
            place_id="place_1",
            origin_lat=37.5,
            origin_lng=127.0,
            destination_lat=37.501,
            destination_lng=127.001,
            requested_at=NOW,
        )
        is None
    )
    assert requests == []


def test_metadata_server_id_token_provider_fetches_audience_token() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="google-id-token")

    provider = MetadataServerIdTokenProvider(
        "https://map-service.example",
        client=httpx.Client(
            base_url="http://metadata.google.internal",
            transport=httpx.MockTransport(handler),
        ),
    )

    assert provider.get_token() == "google-id-token"
    assert requests[0].headers["Metadata-Flavor"] == "Google"
    assert requests[0].url.params["audience"] == "https://map-service.example"


def test_parse_map_route_distance_estimate_defaults_confidence() -> None:
    estimate = parse_map_route_distance_estimate({"route_distance_m": 1000})

    assert estimate.route_distance_m == 1000
    assert estimate.confidence == 0.8


class _TokenProvider:
    def __init__(self, token: str | None) -> None:
        self._token = token

    def get_token(self) -> str | None:
        return self._token
