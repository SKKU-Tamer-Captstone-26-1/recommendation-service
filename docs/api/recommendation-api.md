# Recommendation API

## Purpose

This document defines the public and internal API contracts owned by
`recommendation-service`.

## Document Contract

### Why This File Exists

- Gives gateway, client, backend, and AI contributors one API source of truth.
- Prevents identity and survey ownership mistakes.
- Keeps recommendation responses explainable and reproducible.

### What MUST Be Documented Here

- Public endpoints.
- Internal endpoints.
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
4. Public Endpoints
5. Internal Endpoints
6. Error Model
7. Idempotency
8. Versioning
9. Update Rules

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

- Version public endpoints under `/v1`.
- Keep response fields stable.
- Add fields compatibly when possible.
- Use explicit status values instead of ambiguous empty arrays.
- Include request IDs for traceability.

## Identity Rules

The caller identity is resolved from authenticated context:

```text
JWT sub -> external_user_id
```

`recommendation-service` MUST NOT issue, refresh, or own JWTs.

## Public Endpoints

### `GET /v1/profile/status`

Purpose:

- Return current recommendation profile lifecycle state.

Response:

```json
{
  "status": "active",
  "profile_revision": 4,
  "survey_response_id": "surv_resp_123",
  "generated_at": "2026-05-08T12:10:00Z"
}
```

### `GET /v1/recommendations/beverages`

Purpose:

- Return explainable beverage recommendations for the authenticated user.

Query parameters:

| Name | Required | Meaning |
|---|---|---|
| `category` | no | Filter by beverage category |
| `limit` | no | Result count |
| `budget_mode` | no | `strict` or `soft` |

Response:

```json
{
  "request_id": "rec_req_123",
  "profile_revision": 4,
  "results": [
    {
      "rank": 1,
      "target_type": "beverage",
      "target_id": "bev_123",
      "name": "Example Bourbon",
      "scores": {
        "similarity": 0.87,
        "final": 0.91
      },
      "reason_codes": ["MATCHES_VANILLA_CARAMEL", "BEGINNER_FRIENDLY"],
      "explanation": "Matches your vanilla/caramel preference and beginner-friendly profile."
    }
  ]
}
```

### `GET /v1/recommendations/venues`

Purpose:

- Return explainable venue recommendations for the authenticated user.

Query parameters:

| Name | Required | Meaning |
|---|---|---|
| `lat` | yes | Latitude |
| `lng` | yes | Longitude |
| `radius_m` | no | Search radius in meters |
| `limit` | no | Result count |

### `POST /v1/recommendation-events`

Purpose:

- Record user interactions with recommendation results.

Request:

```json
{
  "request_id": "rec_req_123",
  "result_id": "rec_result_456",
  "event_type": "click",
  "metadata": {}
}
```

Supported interaction types:

```text
impression
click
save
dismiss
detail_view
```

## Internal Endpoints

Internal endpoints are for workers, admin tools, or controlled service calls.

```text
POST /internal/v1/sync/survey-events
POST /internal/v1/profiles/{external_user_id}/regenerate
POST /internal/v1/rebuild/profiles
POST /internal/v1/rebuild/qdrant
GET  /internal/v1/sync/status
```

Internal endpoints MUST NOT be exposed through the public gateway without
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

Interaction events SHOULD accept an idempotency key when clients can retry.
Internal profile regeneration MUST be idempotent by profile generation uniqueness
rules documented in `../recommendation/sync-flow.md`.

