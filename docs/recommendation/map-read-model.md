# Recommendation Map Read Model

## Purpose

This document defines how `recommendation-service` consumes map/place data for
venue recommendations without owning canonical place, menu, inventory, price, or
location state.

## Core Rule

`recommendation-service` stores map/place data only as derived snapshots/read
models.

Canonical ownership remains with map-service/place-service.

## Document Contract

### What MUST Be Documented Here

- Map/place ownership boundary.
- Snapshot sync inputs.
- Recommendation-owned read-model tables.
- Freshness and confidence rules.
- Required recommendation log metadata.
- Purchase-option output strategy.

### What MUST NOT Be Documented Here

- Canonical map-service schema. Use `../map-place/database.md`.
- Map-service admin workflow.
- Full recommendation scoring formula. Use `recommendation-logic.md`.
- Assistant response schema. Use `../assistant/response-schema.md`.

## Allowed Inputs

Recommendation may consume published map/place data through:

- internal gRPC APIs
- durable events
- signed snapshots
- scheduled sync jobs

Forbidden:

- direct map-service database reads
- direct map-service database writes
- treating snapshots as canonical place truth
- reactivating, closing, merging, or editing places

## Events / Sync Inputs

Minimum event types:

```text
place.published
place.updated
place.hidden
place.closed
place.merged
place.deleted
menu.updated
inventory.updated
price.updated
```

The V1 sync input is a paginated map-service/place-service API response. It is
the contract consumed by `recommendation-service`; it is not a canonical map
database schema.

Endpoint:

```text
GET /internal/v1/recommendation/map-snapshot-events?cursor=<cursor>&limit=<limit>
```

Response:

```json
{
  "cursor": "map_cursor_123",
  "next_cursor": "map_cursor_124",
  "has_more": true,
  "snapshot_watermark": "2026-05-22T09:00:00Z",
  "events": []
}
```

Each event MUST include:

```json
{
  "contract_version": "map_snapshot_event_v1",
  "event_id": "map_evt_123",
  "event_type": "inventory.updated",
  "occurred_at": "2026-05-22T09:00:00Z",
  "place_id": "place_123",
  "place_revision": "place_rev_12",
  "trace_id": "trace_123",
  "venue": {
    "name": "Example Bottle Shop",
    "place_type": "bottle_shop",
    "address": "Seoul, Gangnam-gu",
    "lat": 37.5001,
    "lng": 127.0276,
    "status": "active",
    "publication_status": "published",
    "stale_after": "2026-05-30T00:00:00Z"
  },
  "menus": [
    {
      "menu_item_id": "menu_123",
      "menu_revision": "menu_rev_7",
      "beverage_item_id": "11111111-1111-4111-8111-111111111111",
      "source_beverage_id": "map_bev_123",
      "menu_name": "Example Bourbon",
      "menu_type": "bottle",
      "status": "active"
    }
  ],
  "inventory": [
    {
      "inventory_revision": "inv_rev_8",
      "beverage_item_id": "11111111-1111-4111-8111-111111111111",
      "source_beverage_id": null,
      "availability_status": "available",
      "confidence": 0.9,
      "last_seen_at": "2026-05-22T09:00:00Z",
      "expires_at": "2026-05-25T09:00:00Z"
    }
  ],
  "prices": [
    {
      "price_revision": "price_rev_3",
      "beverage_item_id": "11111111-1111-4111-8111-111111111111",
      "menu_item_id": "menu_123",
      "price_krw": 42000,
      "price_type": "retail",
      "confidence": 0.85,
      "valid_from": "2026-05-22T00:00:00Z",
      "valid_until": "2026-05-30T00:00:00Z"
    }
  ]
}
```

Required event fields:

| Field | Rule |
|---|---|
| `contract_version` | Required. Must be `map_snapshot_event_v1` for this contract. |
| `event_id` | Required idempotency key. |
| `event_type` | Required. Must be one of the supported event types above. |
| `occurred_at` | Required source event timestamp. |
| `place_id` | Required canonical map/place identifier. |
| `place_revision` | Required source revision for the venue snapshot. |
| `venue.lat` / `venue.lng` | Required WGS84 coordinates for MVP distance scoring. Top-level `lat` / `lng` may be accepted only for backwards-compatible local fixtures. |
| `venue.status` | Required source lifecycle status. |
| `venue.publication_status` | Required publication state for ranking eligibility. |
| `menus[].menu_revision` | Required when menu rows are present. |
| `menus[].source_beverage_id` | Optional map-service/source catalog key when no recommendation `beverage_item_id` mapping exists yet. |
| `inventory[].inventory_revision` | Required when inventory rows are present. |
| `prices[].price_revision` | Required when price rows are present. |
| `inventory[].confidence` | Required confidence in range `0.0..1.0`. |
| `prices[].confidence` | Required confidence in range `0.0..1.0`. |
| `snapshot_watermark` | Required on paginated responses. Records the map-service snapshot/replay watermark for observability. |

Lifecycle handling:

| Source status | Recommendation read-model handling |
|---|---|
| `active` + `published` | Eligible if menu/inventory/price filters pass. |
| `hidden` | Store snapshot but exclude from ranking. |
| `closed` | Store snapshot but exclude from ranking. |
| `duplicate_merged` | Store snapshot but exclude from ranking. |
| `archived` | Store snapshot but exclude from ranking. |
| `rejected` | Store snapshot but exclude from ranking. |
| `deleted` | Treat as archived/ineligible read model state; do not hard-delete recommendation snapshots. |

The sync worker MUST NOT reactivate, close, merge, archive, or edit canonical
places. Closed, archived, and duplicate-merged source statuses remain canonical
map-service/place-service decisions.

`place.deleted` events from map-service/place-service are tombstone signals for
the recommendation read model. They MUST preserve event payload and source
revision metadata, mark the derived snapshot ineligible, and keep historical
recommendation logs explainable.

## Read-Model Tables

Read-model table definitions are owned by `../database/erd.md`.

Required conceptual tables:

```text
venue_snapshots
venue_menu_snapshots
venue_inventory_snapshots
venue_price_snapshots
map_snapshot_sync_cursors
map_snapshot_sync_events
```

These tables MUST include:

- external map/place identifiers
- source revision IDs
- snapshot payload or hash
- sync timestamp
- freshness or expiry metadata
- confidence metadata when source data is uncertain

`map_snapshot_sync_*` tables store recommendation-service sync cursors, event
payloads, retry state, and idempotency keys. They are not canonical map/place
tables.

## Freshness Policy

Venue recommendations MUST consider freshness.

Recommended MVP policy:

| Data | Fresh | Stale | Exclude By Default |
|---|---:|---:|---:|
| inventory | <= 3 days | > 7 days | >= 30 days |
| price | valid_until not expired | expired or unknown | expired by > 30 days |
| place status | latest revision | unknown revision | hidden, closed, merged |

Stale data MAY be returned only when the response clearly marks uncertainty and
the scoring config permits it.

## Venue Recommendation Facts

Venue recommendation results SHOULD expose:

- place id
- place name
- place type
- distance meters
- estimated travel time if available
- route complexity if available
- beverage id or selected item id
- availability status
- inventory confidence
- price
- price confidence
- place revision
- inventory revision
- price revision
- snapshot synced time
- freshness status

Venue recommendation requests MAY filter by map/place snapshot `place_type`.
This is a request-level read-model constraint only. recommendation-service does
not create canonical place taxonomy and does not write place/menu/inventory/price
state. Alias values such as `store`, `bar`, and `outdoor` are resolved to known
snapshot place-type values before ranking, while the response preserves the
original snapshot `place_type`.

## Recommendation Logs

Recommendation logs MUST include snapshot revision data.

```text
recommendation_requests
- request_id
- external_user_id from auth context
- profile_revision_id
- selected_beverage_id if applicable
- request_context_json
- created_at

recommendation_results
- request_id
- rank
- target_type
- target_id
- recommended_place_id
- place_revision
- inventory_revision
- price_revision
- score_breakdown_json
- reason_codes
- created_at
```

Logs MUST preserve enough metadata to explain why a venue was recommended later,
even if map-service later updates the canonical place.

## Selected Beverage Purchase Options

When a user selects a beverage, recommendation should provide differentiated
options:

```text
nearest_reasonable
best_price
balanced_best
```

Scoring inputs may include:

- taste match
- distance
- estimated travel time
- route complexity
- price
- availability confidence
- inventory freshness
- price freshness
- venue quality

Do not return several near-identical top-scoring venues when the product request
expects meaningful alternatives.

Selected-beverage venue recommendations use an injected distance provider.
The default provider returns straight-line distance labeled as
`distance_strategy = straight_line_mvp`. When the approved map-service route
adapter is enabled, route-aware results are labeled as
`distance_strategy = map_route_estimate_v1` and straight-line fallback is marked
explicitly.

## Distance Feature Contract

Venue scoring must receive distance as an explicit feature, not as an implicit
hardcoded calculation hidden inside ranking.

Current default:

```text
strategy = straight_line_mvp
source = venue_snapshot_coordinates
is_route_distance = false
confidence = 0.45
```

This means `distance_m` is a WGS84 haversine straight-line distance between the
authenticated request lat/lng and the venue snapshot coordinates. It is useful
for MVP ranking and radius filtering, but it is not walking distance, driving
distance, route time, public-transit time, or accessibility.

Venue recommendation metadata MUST preserve:

```text
distance_m
distance_strategy
distance_source
distance_confidence
is_route_distance
distance_fallback_used
straight_line_distance_m
route_distance_m
route_duration_seconds
route_complexity
```

Future map-service route integration should provide a route-aware distance
feature through an adapter/provider boundary:

```text
strategy = map_route_estimate_v1
source = map_service_route_api
is_route_distance = true
route_distance_m = <meters from route provider>
route_duration_seconds = <estimated travel time if available>
route_complexity = <simple | moderate | complex if available>
```

The route adapter/provider must be injected into `BeverageRecommendationService`
through the service boundary. Request logs must preserve the selected provider
policy and the strategies used by returned results:

```text
distance_provider_policy = service_injected_provider_v1
distance_strategy = straight_line_mvp | map_route_estimate_v1 | mixed_distance_strategy | no_distance_results
distance_strategies = [...]
distance_sources = [...]
is_route_distance = true | false
distance_fallback_used = true | false
distance_result_count = <returned venue result count>
route_distance_result_count = <results using map-service route estimates>
straight_line_distance_result_count = <results using straight-line distance>
fallback_distance_result_count = <results where route lookup failed and fallback was used>
unknown_distance_result_count = <results with an unclassified distance strategy>
distance_route_coverage = <route_distance_result_count / distance_result_count>
distance_strategy_counts = {"map_route_estimate_v1": 1, "straight_line_mvp": 1}
distance_source_counts = {"map_service_route_api": 1, "venue_snapshot_coordinates": 1}
```

`MapRouteDistanceProvider` is the recommendation-service adapter base for a
future map-service route client. It does not own route facts and it does not
read map-service storage. A future gRPC or HTTP client should implement this
protocol-like contract:

```text
route_distance(
  place_id,
  origin_lat,
  origin_lng,
  destination_lat,
  destination_lng,
  requested_at
) -> MapRouteDistanceEstimate | None
```

`MapRouteDistanceEstimate` is converted into `VenueDistanceFeature` with:

```text
strategy = map_route_estimate_v1
source = map_service_route_api
is_route_distance = true
distance_m = route_distance_m
straight_line_distance_m = haversine(origin, venue snapshot coordinates)
```

`None` means map-service could not produce a route estimate for that candidate.
When wrapped with `FallbackVenueDistanceProvider`, the service then falls back to
`straight_line_mvp`.

Runtime provider wiring uses `create_venue_distance_provider(settings, route_client=...)`:

```text
MAP_ROUTE_DISTANCE_ENABLED=false
  -> StraightLineVenueDistanceProvider

MAP_ROUTE_DISTANCE_ENABLED=true with route_client
  -> FallbackVenueDistanceProvider(
       primary=MapRouteDistanceProvider(route_client),
       fallback=StraightLineVenueDistanceProvider()
     )

MAP_ROUTE_DISTANCE_ENABLED=true without route_client
  -> StraightLineVenueDistanceProvider and warning log
```

Runtime gRPC construction now creates an HTTP route client when
`MAP_ROUTE_DISTANCE_ENABLED=true`. The client calls map-service through the
approved service API boundary; it does not read map-service storage.

HTTP route request:

```http
POST /internal/v1/recommendation/route-distance
```

```json
{
  "contract_version": "map_route_distance_request_v1",
  "place_id": "place_123",
  "origin": {"lat": 37.5, "lng": 127.0},
  "destination": {"lat": 37.501, "lng": 127.001},
  "requested_at": "2026-06-08T12:00:00+00:00"
}
```

HTTP route response:

```json
{
  "route_distance_m": 780.4,
  "route_duration_seconds": 520,
  "route_complexity": "simple",
  "confidence": 0.88
}
```

`204`, `404`, request timeout, malformed payload, or failed private Cloud Run ID
token lookup means no usable route estimate for that candidate. With fallback
enabled, the service then uses `straight_line_mvp` for that candidate and
preserves fallback metadata in the result and request log.

If map-service is private on Cloud Run, set:

```text
MAP_SERVICE_SERVERLESS_AUDIENCE=https://<map-service-cloud-run-url>
```

The route client fetches a Google ID token from the Cloud Run metadata server
and sends it as:

```text
x-serverless-authorization: Bearer <google-id-token>
```

The gRPC server path passes the configured provider into
`BeverageRecommendationService`, so the ranking path does not need to change
when the real map-service client is added.

When the future map-service route adapter cannot produce a route estimate for a
candidate, it should return no distance feature for that candidate and be wrapped
with `FallbackVenueDistanceProvider`. The fallback provider uses the current
`StraightLineVenueDistanceProvider` so a partial map-service route failure does
not erase otherwise valid recommendation candidates.

Injected distance provider output is validated before scoring. Invalid primary
provider output is treated as missing so `FallbackVenueDistanceProvider` can use
straight-line fallback. Invalid final provider output excludes the candidate from
venue ranking.

Provider output validation:

```text
distance_m must be finite and >= 0
strategy/source must be non-empty strings
confidence must be finite and between 0 and 1
is_route_distance must be boolean
distance_fallback_used must be boolean

if is_route_distance=true:
  route_distance_m must be finite and >= 0
  distance_m must match route_distance_m
  route_duration_seconds, if present, must be >= 0
  straight_line_distance_m, if present, must be finite and >= 0

if is_route_distance=false:
  straight_line_distance_m must be finite and >= 0
  distance_m must match straight_line_distance_m
  route_distance_m must be null
  route_duration_seconds must be null
```

If some returned results use route distance and others fall back to straight-line
distance, request logs MUST report:

```text
distance_strategy = mixed_distance_strategy
distance_strategies = ["map_route_estimate_v1", "straight_line_mvp"]
distance_sources = ["map_service_route_api", "venue_snapshot_coordinates"]
is_route_distance = true
distance_fallback_used = <per-result metadata only>
distance_result_count = 2
route_distance_result_count = 1
straight_line_distance_result_count = 1
fallback_distance_result_count = 1
unknown_distance_result_count = 0
distance_route_coverage = 0.5
distance_strategy_counts = {"map_route_estimate_v1": 1, "straight_line_mvp": 1}
distance_source_counts = {"map_service_route_api": 1, "venue_snapshot_coordinates": 1}
```

If no venue candidates are returned, request logs MUST use:

```text
distance_strategy = no_distance_results
distance_result_count = 0
route_distance_result_count = 0
straight_line_distance_result_count = 0
distance_route_coverage = 0.0
```

Flutter, gateway, and chatbot-service must inspect per-result metadata before
describing distance. They must not describe a fallback straight-line result as a
route distance.

`recommendation-service` still owns ranking and score breakdowns. map-service
owns canonical route/place facts. Flutter, gateway, and chatbot-service must not
rewrite straight-line distance into route distance.

## Rebuild Strategy

Map/place read models are rebuildable.

Rebuild source priority:

1. map-service/place-service snapshot API
2. map-service/place-service event replay
3. latest approved export from map-service/place-service

Qdrant venue/menu vectors MUST be rebuilt from PostgreSQL read-model snapshots
and canonical recommendation vectors, not from Qdrant payloads.

## Update Rules

- Update this document when map-service event contracts, freshness policy,
  snapshot fields, or venue recommendation tradeoffs change.
- Update `../database/erd.md` before creating migrations for read-model tables.
- Update `recommendation-logic.md` when freshness or confidence affects scoring.
