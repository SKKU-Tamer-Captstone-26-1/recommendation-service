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

Public RPC requests MUST NOT contain `user_id` or `external_user_id` fields.

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
      "explanation": "Matches your vanilla/caramel preference and beginner-friendly profile.",
      "metadata": {
        "style": "bourbon",
        "similarity_score": 0.87,
        "score_breakdown": {}
      }
    }
  ]
}
```

### `RecommendationService.GetVenueRecommendations`

Purpose:

- Return explainable venue recommendations for the authenticated user.

Request fields:

| Name | Required | Meaning |
|---|---|---|
| `lat` | yes | Latitude |
| `lng` | yes | Longitude |
| `radius_m` | no | Search radius in meters |
| `limit` | no | Result count |
| `selected_beverage_id` | yes | Active canonical beverage the user wants to buy or drink |
| `budget_mode` | no | `BUDGET_MODE_SOFT` or `BUDGET_MODE_STRICT` |

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
          "distance_strategy": "straight_line_mvp"
        }
      }
    }
  ]
}
```

Venue results MUST be generated from map/place read-model snapshots documented
in `../recommendation/map-read-model.md`.

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
