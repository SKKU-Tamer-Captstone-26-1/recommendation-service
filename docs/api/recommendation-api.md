# Recommendation gRPC API

## Purpose

This document defines the gRPC-first public and internal API contracts owned by
`recommendation-service`.

## Document Contract

### Why This File Exists

- Gives gateway, client, backend, and AI contributors one API source of truth.
- Prevents identity and survey ownership mistakes.
- Keeps recommendation responses explainable and reproducible.

### What MUST Be Documented Here

- Public gRPC services and RPCs.
- Internal gRPC services and RPCs.
- Auth/JWT expectations.
- Request and response shapes.
- Error/status responses.
- Idempotency behavior.
- Versioning rules.

### What MUST NOT Be Documented Here

- Survey-service API internals beyond dependency references.
- Database table details.
- Full ranking formulas.
- Raw survey answer schemas.

### Recommended Sections

1. Purpose
2. API Principles
3. Identity Rules
4. Operational Endpoints
5. Public Endpoints
6. Internal Endpoints
7. Error Model
8. Idempotency
9. Versioning
10. Update Rules

### Engineering Constraints

- Public APIs MUST NOT accept `external_user_id` as client input.
- User identity MUST come from JWT/gateway-authenticated context.
- Recommendation responses MUST include explanation metadata.
- APIs MUST distinguish missing, pending, stale, and failed profile states.
- Internal APIs MUST be protected from public client access.

### Update Rules

- Update when endpoint paths, schemas, auth behavior, or error codes change.
- Keep examples minimal and synchronized with implementation.

## API Principles

- Version protobuf packages with `ontheblock.recommendation.v1`.
- Keep response fields stable.
- Add fields compatibly when possible.
- Use explicit status values instead of ambiguous empty arrays.
- Include request IDs for traceability.
- Do not generate code from temporary proto drafts.
- Keep `proto/recommendation/v1/recommendation.proto` synchronized with this
  document.

## Identity Rules

The caller identity is resolved from authenticated context:

```text
JWT sub -> external_user_id
```

`recommendation-service` MUST NOT issue, refresh, or own JWTs.

Deployed staging validates bearer tokens by calling auth-service gRPC
`ValidateToken` (`AUTH_TOKEN_VALIDATION_MODE=grpc`). JWKS verification is kept
only as an explicit fallback mode for environments where auth-service exposes an
HTTP JWKS endpoint.

Public RPC requests MUST NOT contain `user_id` or `external_user_id` fields.

Production mobile traffic is expected to arrive through `app-gateway-service`.
When `recommendation-service` is private on Cloud Run, the gateway must preserve
the user token and add Cloud Run IAM metadata separately:

```text
authorization: Bearer <auth-service-jwt>
x-serverless-authorization: Bearer <google-id-token-for-recommendation-service>
```

`authorization` is consumed by recommendation-service for user context.
`x-serverless-authorization` is consumed by Cloud Run for service-to-service IAM.

## gRPC Services

The initial `recommendation.proto` is defined for the beverage-first production
slice. Current service shape:

```proto
service RecommendationService {
  rpc GetProfileStatus(GetProfileStatusRequest) returns (GetProfileStatusResponse);
  rpc GetBeverageRecommendations(GetBeverageRecommendationsRequest) returns (GetBeverageRecommendationsResponse);
  rpc GetVenueRecommendations(GetVenueRecommendationsRequest) returns (GetVenueRecommendationsResponse);
  rpc RecordRecommendationEvent(RecordRecommendationEventRequest) returns (RecordRecommendationEventResponse);
}
```

The initial production beverage slice defines this contract at:

```text
proto/recommendation/v1/recommendation.proto
```

Python gRPC bindings live under:

```text
app/grpc/gen/
```

Assistant API drafts are documented separately in
`../assistant/response-schema.md`. Do not merge assistant RPCs into
`RecommendationService` unless a future architecture decision explicitly places
assistant runtime inside this repository.

`GetVenueRecommendations` is implemented only for selected-beverage venue
ranking from map/place read-model snapshots. It must not read or mutate
map-service/place-service databases directly.

Internal operations SHOULD be separated from public recommendation reads:

```proto
service RecommendationAdminService {
  rpc SyncSurveyEvents(SyncSurveyEventsRequest) returns (SyncSurveyEventsResponse);
  rpc RegenerateProfile(RegenerateProfileRequest) returns (RegenerateProfileResponse);
  rpc RebuildProfiles(RebuildProfilesRequest) returns (RebuildProfilesResponse);
  rpc RebuildQdrant(RebuildQdrantRequest) returns (RebuildQdrantResponse);
  rpc GetSyncStatus(GetSyncStatusRequest) returns (GetSyncStatusResponse);
}
```

## Operational Endpoints

Operational HTTP endpoints expose service health and runtime status. They MUST
NOT return user taste data, raw survey data, secrets, or recommendation results.

The gRPC server also exposes the standard `grpc.health.v1.Health` service.

### `GET /health/live`

Purpose:

- Process liveness check.

### `GET /health/ready`

Purpose:

- Dependency readiness check for PostgreSQL and Qdrant.

### `GET /v1/status`

Purpose:

- Return non-sensitive service configuration status such as active vector,
  mapper, and scoring version names.

## Public RPCs

### `RecommendationService.GetProfileStatus`

Purpose:

- Return current recommendation profile lifecycle state.

Response shape:

```json
{
  "status": "active",
  "profile_revision": 4,
  "survey_response_id": "surv_resp_123",
  "generated_at": "2026-05-08T12:10:00Z"
}
```

### `RecommendationService.GetBeverageRecommendations`

Purpose:

- Return explainable beverage recommendations for the authenticated user.

Request fields:

| Name | Required | Meaning |
|---|---|---|
| `category` | no | Filter by beverage category |
| `limit` | no | Result count |
| `budget_mode` | no | `BUDGET_MODE_SOFT` or `BUDGET_MODE_STRICT` |
| `exclude_beverage_ids` | no | Beverage UUIDs that must not be returned, usually previous chatbot results |
| `exclude_result_ids` | no | Recommendation result UUIDs whose beverage targets must not be returned |
| `diversity_mode` | no | Follow-up diversity intent: `STANDARD`, `DIFFERENT`, or `ADJACENT` |
| `flavor_direction` | no | Taste-direction follow-up intent such as `SWEETER`, `SMOKIER`, or `LIGHTER` |

Supported beverage diversity modes:

| Mode | Meaning |
|---|---|
| `BEVERAGE_DIVERSITY_MODE_STANDARD` | Default ranked beverage recommendation behavior |
| `BEVERAGE_DIVERSITY_MODE_DIFFERENT` | Avoid excluded beverages and, when possible, avoid their dominant style/category |
| `BEVERAGE_DIVERSITY_MODE_ADJACENT` | Avoid excluded beverages while preferring a non-identical style close to the user's preferred category |

Chatbot follow-up usage:

```text
User: 다른 술 추천해줘
chatbot-service:
  - reads previous recommendation result IDs from its conversation state
  - calls GetBeverageRecommendations with exclude_result_ids
  - sets diversity_mode = BEVERAGE_DIVERSITY_MODE_DIFFERENT
recommendation-service:
  - resolves result IDs to beverage IDs
  - excludes those beverage IDs
  - returns a deterministic ranked list
```

The gateway and chatbot-service must not rerank, invent candidates, or apply
business recommendation logic outside this RPC. If exclusions remove all
eligible candidates, the service may return fewer results instead of fabricating
a fallback.

Supported beverage flavor directions:

| Direction | Meaning |
|---|---|
| `BEVERAGE_FLAVOR_DIRECTION_SWEETER` | Prefer sweeter, dessert-like, or rounded candidates |
| `BEVERAGE_FLAVOR_DIRECTION_LESS_SWEET` | Prefer less sweet candidates with drier/brighter signals |
| `BEVERAGE_FLAVOR_DIRECTION_SMOKIER` | Prefer smoky, peated, roasted, or stronger smoke-adjacent candidates |
| `BEVERAGE_FLAVOR_DIRECTION_LESS_SMOKY` | Prefer less smoky candidates while allowing brighter/floral/fruity signals |
| `BEVERAGE_FLAVOR_DIRECTION_LIGHTER` | Prefer lighter body and lower intensity with acidity/carbonation where available |
| `BEVERAGE_FLAVOR_DIRECTION_RICHER` | Prefer fuller body, oak, dried fruit, and richer texture |
| `BEVERAGE_FLAVOR_DIRECTION_MORE_HERBAL_BITTER` | Prefer herbal, botanical, and bitter profiles |
| `BEVERAGE_FLAVOR_DIRECTION_BRIGHTER_FRUITY` | Prefer fruitier, brighter, and more acidic profiles |

Chatbot flavor follow-up usage:

```text
User: 피트향은 줄이고 더 가벼운 걸로 추천해줘
chatbot-service:
  - keeps previous result IDs in exclude_result_ids when appropriate
  - sets flavor_direction = BEVERAGE_FLAVOR_DIRECTION_LIGHTER
  - may also use diversity_mode = BEVERAGE_DIVERSITY_MODE_ADJACENT
recommendation-service:
  - applies deterministic request-level score adjustment
  - stores flavor_direction in request logs and result metadata
  - returns server-owned ranking and reason codes
```

`flavor_direction` does not mutate the stored taste profile. It is a request
control, and the service records its `beverage_flavor_direction_v1` policy in
the response metadata under `source.model_features.flavor_direction_feature`.

Response:

```json
{
  "request_id": "rec_req_123",
  "profile_status": "PROFILE_STATUS_ACTIVE",
  "profile_revision": 4,
  "recommendations": [
    {
      "rank": 1,
      "result_id": "rec_result_456",
      "beverage_id": "bev_123",
      "name_ko": "Example Bourbon",
      "name_en": "Example Bourbon",
      "category": "whiskey",
      "score": 0.91,
      "reason_codes": ["MATCHES_VANILLA_CARAMEL", "BEGINNER_FRIENDLY"],
      "explanation": "Example Bourbon은(는) bourbon 계열로, 현재 취향 프로필과 잘 맞는 추천입니다. 달콤한 바닐라와 캐러멜 느낌을 선호하는 취향에 맞습니다. 처음 마시는 사람도 비교적 부담 없이 접근하기 좋습니다.",
      "metadata": {
        "style": "bourbon",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Glass_of_whisky.jpg",
        "image_alt_text_ko": "위스키 잔 대표 이미지",
        "image": {
          "policy_version": "beverage_image_v1",
          "image_kind": "category_representative",
          "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Glass_of_whisky.jpg",
          "original_image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Glass_of_whisky.jpg",
          "cache_key": "beverage-images/v1/bev_image_whiskey_category_representative_001.jpg",
          "cache_policy": "operator_managed_image_cache_v1",
          "display_url_source": "licensed_source_url",
          "source_url": "https://commons.wikimedia.org/wiki/File:Glass_of_whisky.jpg",
          "license": "Public Domain",
          "attribution": "Chris huh / Wikimedia Commons",
          "attribution_required": false,
          "display_policy": "allowed_mvp_display_with_license_metadata"
        },
        "similarity_score": 0.87,
        "score_breakdown": {},
        "source": {
          "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Glass_of_whisky.jpg",
          "image": {
            "policy_version": "beverage_image_v1",
            "image_kind": "category_representative"
          },
          "model_features": {
            "budget_fit": 0.82,
            "budget_feature": {
              "strategy": "catalog_price_range_soft_v1",
              "evidence": "catalog_price_range",
              "confidence": 0.65,
              "budget_range": "30000_100000",
              "price_min_krw": 39000,
              "price_max_krw": 45000,
              "price_policy": "verified_krw_observations_not_live_truth"
            },
            "budget_tradeoff": {
              "policy_version": "beverage_budget_tradeoff_v1",
              "status": "within_budget",
              "display_label_ko": "예산 적합",
              "note_ko": "검증된 카탈로그 가격대가 선택한 예산 구간과 겹칩니다.",
              "source": "catalog_price_not_live_offer"
            }
          }
        }
      }
    }
  ]
}
```

`budget_feature` is a soft catalog signal. It is not a live store price, menu
price, inventory fact, or strict affordability guarantee.
`budget_tradeoff` is display-ready explanation metadata derived from the same
soft catalog signal. Flutter and chatbot-service may show `display_label_ko`
and `note_ko`, but must not treat it as live price or stock truth.

`image_url` is the app display URL for recommendation cards. MVP image metadata
may be a source-checked direct product/cocktail representative image or a
category fallback. In local seed data the display URL may be the licensed source
URL. In staging/production seed promotion, operators can set
`BEVERAGE_IMAGE_CDN_BASE_URL` so `image_url` points to the ONTHEBLOCK-managed
image cache while `metadata.image.original_image_url`, `source_url`, license,
and attribution fields preserve traceability.

Flutter may display `metadata.image_url` directly, but it must preserve
`metadata.image` license/attribution fields for a detail or credits surface when
attribution is required. Image presence, cache status, or image kind must not
affect ranking, filtering, inventory display, or recommendation confidence.

### `RecommendationService.GetVenueRecommendations`

Purpose:

- Return explainable venue recommendations for the authenticated user.

Request fields:

| Name | Required | Meaning |
|---|---|---|
| `lat` | yes | User-origin WGS84 latitude forwarded by Flutter/gateway |
| `lng` | yes | User-origin WGS84 longitude forwarded by Flutter/gateway |
| `radius_m` | no | Search radius in meters |
| `limit` | no | Result count |
| `selected_beverage_id` | yes | Active canonical beverage the user wants to buy or drink |
| `budget_mode` | no | `BUDGET_MODE_SOFT` or `BUDGET_MODE_STRICT` |
| `place_types` | no | Optional place-type filter such as `bar`, `store`, `liquor_shop`, `bottle_shop`, or `outdoor` |

`lat` and `lng` must be precise coordinates from the mobile location flow,
map picker, or an approved auth/gateway user-location metadata contract. The
current auth proto exposes `neighborhood` for profile display, but
`recommendation-service` must not infer coordinates from that text field or read
auth-service storage. If the gateway cannot provide precise coordinates, it
should return a location-needed state instead of sending placeholder values.

Kakao map keys and raw Kakao lookup payloads are not part of this RPC.
Flutter/map-service may use Kakao for lookup/display under the Kakao policy, but
venue ranking uses structured request coordinates plus map/place read-model
snapshots and the approved map-service route-distance API.

`place_types` is a request-level constraint over map/place read-model snapshot
metadata. It does not create or edit canonical place taxonomy. Friendly aliases
are resolved by recommendation-service before ranking:

| Request value | Matched snapshot `place_type` values |
|---|---|
| `store` / `shop` | `bottle_shop`, `liquor_shop`, `store` |
| `bar` | `bar`, `cocktail_bar`, `pub`, `whiskey_bar`, `wine_bar` |
| `pub` | `pub`, `bar` |
| `outdoor` | `outdoor_spot`, `outdoor` |

Unknown values are rejected as invalid requests so Flutter, gateway, and
chatbot contracts do not silently drift.

Response:

```json
{
  "request_id": "rec_req_venue_123",
  "profile_status": "PROFILE_STATUS_ACTIVE",
  "profile_revision": 4,
  "recommendations": [
    {
      "rank": 1,
      "result_id": "rec_result_456",
      "place_id": "place_123",
      "name": "Example Bottle Shop",
      "place_type": "bottle_shop",
      "option_type": "balanced_best",
      "distance_m": 720,
      "price_krw": 42000,
      "availability_status": "VENUE_AVAILABILITY_STATUS_LIKELY_AVAILABLE",
      "freshness_status": "VENUE_FRESHNESS_STATUS_FRESH",
      "score": 0.89,
      "reason_codes": ["NEARBY_VENUE", "WITHIN_BUDGET", "BALANCED_BEST"],
      "explanation": "Example Bottle Shop is recommended because: nearby venue, within budget, balanced best.",
      "metadata": {
        "score_breakdown": {},
        "source": {
          "place_revision": "place_rev_12",
          "menu_revision": "menu_rev_7",
          "inventory_revision": "inv_rev_8",
          "price_revision": "price_rev_3",
          "distance_m": 720,
          "distance_strategy": "straight_line_mvp",
          "distance_source": "venue_snapshot_coordinates",
          "distance_confidence": 0.45,
          "is_route_distance": false,
          "distance_fallback_used": false,
          "straight_line_distance_m": 720,
          "route_distance_m": null,
          "route_duration_seconds": null,
          "route_complexity": null
        }
      }
    }
  ]
}
```

Venue results MUST be generated from map/place read-model snapshots documented
in `../recommendation/map-read-model.md`.

`distance_m` is interpreted by `metadata.source.distance_strategy`.
`straight_line_mvp` is not a real route estimate. Flutter, gateway, and
chatbot-service must not relabel it as walking, driving, or transit distance.
When a future map-service route provider is approved, the same metadata surface
can report `is_route_distance=true`, `route_distance_m`,
`route_duration_seconds`, and `route_complexity`.

Runtime route distance is controlled by:

```text
MAP_ROUTE_DISTANCE_ENABLED
MAP_ROUTE_DISTANCE_PATH
MAP_ROUTE_DISTANCE_TIMEOUT_SECONDS
MAP_ROUTE_DISTANCE_FALLBACK_ENABLED
MAP_SERVICE_SERVERLESS_AUDIENCE
```

When enabled, recommendation-service calls the approved map-service route API
and converts the response into the existing `VenueDistanceFeature` metadata. A
missing route response, timeout, malformed payload, or failed private Cloud Run
ID token lookup falls back to `straight_line_mvp` when fallback is enabled.
Clients must inspect each result's `metadata.source.is_route_distance` before
displaying route-style copy. `metadata.source.distance_fallback_used=true`
means a route lookup was attempted but the service returned a straight-line
fallback result instead.

Supported venue option types:

```text
VENUE_OPTION_TYPE_NEAREST_REASONABLE
VENUE_OPTION_TYPE_BEST_PRICE
VENUE_OPTION_TYPE_BALANCED_BEST
```

### `RecommendationService.RecordRecommendationEvent`

Purpose:

- Record user interactions with recommendation results.

Request:

```json
{
  "request_id": "rec_req_123",
  "result_id": "rec_result_456",
  "event_type": "RECOMMENDATION_EVENT_TYPE_CLICK",
  "idempotency_key": "event_rec_req_123_rec_result_456_click_1",
  "metadata": {
    "client_platform": "flutter",
    "app_version": "1.0.0",
    "surface": "home_recommendation_card",
    "session_id_hash": "sha256:...",
    "list_position": 1,
    "visible_ms": 2300,
    "source": "client"
  }
}
```

Supported interaction types:

```text
RECOMMENDATION_EVENT_TYPE_IMPRESSION
RECOMMENDATION_EVENT_TYPE_CLICK
RECOMMENDATION_EVENT_TYPE_SAVE
RECOMMENDATION_EVENT_TYPE_DISMISS
RECOMMENDATION_EVENT_TYPE_DETAIL_VIEW
```

`request_id` and `result_id` must reference recommendation-owned request/result
records returned by recommendation APIs.

Client-generated feedback in staging and production MUST include
`idempotency_key`. The key should be stable for one logical event retry and
unique across different events. The service deduplicates by idempotency key.

Allowed metadata keys:

| Key | Type | Meaning |
|---|---|---|
| `client_platform` | string | Client platform, for example `flutter`, `ios`, `android`, or `web` |
| `app_version` | string | Client application version |
| `surface` | string | Product surface where the recommendation appeared |
| `session_id_hash` | string | Hashed session identifier, never a raw session token |
| `list_position` | integer | Position shown to the user |
| `visible_ms` | integer | Approximate visible duration in milliseconds |
| `source` | string | Event source, for example `client`, `chat`, `load_test`, or `system` |

Metadata MUST NOT include raw PII, tokens, auth headers, raw user IDs, raw
session IDs, names, email addresses, or phone numbers. Unsupported metadata keys
are rejected instead of silently stored.

## Internal RPCs

Internal RPCs are for workers, admin tools, or controlled service calls.

```text
RecommendationAdminService.SyncSurveyEvents
RecommendationAdminService.RegenerateProfile
RecommendationAdminService.RebuildProfiles
RecommendationAdminService.RebuildQdrant
RecommendationAdminService.GetSyncStatus
```

Internal RPCs MUST NOT be exposed through the public gateway without
authorization controls.

## Error Model

Common response:

```json
{
  "error": {
    "code": "PROFILE_PENDING",
    "message": "Taste profile generation is pending.",
    "request_id": "req_123"
  }
}
```

Required profile-state errors:

| Code | Meaning |
|---|---|
| `PROFILE_MISSING` | User has no completed profile source |
| `PROFILE_PENDING` | Generation is in progress |
| `PROFILE_STALE` | Older profile served or regeneration pending |
| `PROFILE_FAILED` | Generation failed |

## Idempotency

Client-generated interaction events in staging and production MUST include an
idempotency key when clients can retry. Local tools and tests should include one
unless they are explicitly testing missing-key behavior.

Internal profile regeneration MUST be idempotent by profile generation uniqueness
rules documented in `../recommendation/sync-flow.md`.
