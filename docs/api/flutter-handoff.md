# Flutter Recommendation Handoff

## Purpose

This document gives Flutter the staging contract for calling
`recommendation-service` after the Plan 012 Cloud Run deployment.

## Endpoint

Staging gRPC host:

```text
recommendation-service-vcuepibcwq-du.a.run.app:443
```

Public Cloud Run URL:

```text
https://recommendation-service-vcuepibcwq-du.a.run.app
```

Protocol:

```text
gRPC over TLS
```

## Auth Metadata

Every recommendation RPC except standard gRPC health must include the JWT issued
by `auth-service`:

```text
authorization: Bearer <auth-service-jwt>
```

Flutter must not send `user_id` or `external_user_id` in recommendation
requests. `recommendation-service` resolves the user from JWT `sub`.

Current deployed smoke evidence:

```text
cloud_run_revision = recommendation-service-00002-v8w
grpc_health = SERVING
GetProfileStatus without bearer token = UNAUTHENTICATED
```

## Proto

Source proto:

```text
proto/recommendation/v1/recommendation.proto
```

Python generated bindings are committed under:

```text
app/grpc/gen/
```

Flutter should generate Dart gRPC bindings from the same proto package:

```text
ontheblock.recommendation.v1
```

## Recommended Call Order

1. `GetProfileStatus`
2. `GetBeverageRecommendations`
3. `GetVenueRecommendations` only after map/place snapshot data exists
4. `RecordRecommendationEvent`

If `GetProfileStatus` is not active, Flutter should show the survey/profile
pending state instead of requesting recommendations.

## Beverage Request

Minimal staging request:

```text
GetBeverageRecommendations(
  category: "",
  limit: 10,
  budget_mode: BUDGET_MODE_SOFT
)
```

Strict budget mode is intentionally unavailable until approved canonical
price/map snapshot semantics are deployed.

## Feedback Events

Allowed `metadata` keys for `RecordRecommendationEvent`:

```text
client_platform
app_version
surface
session_id_hash
list_position
visible_ms
source
```

Use a stable idempotency key per client event:

```text
<session_id_hash>:<result_id>:<event_type>
```

## Current Caveats

- Deployed survey-service does not yet expose cursor-based
  `ListSurveyEvents` / `GetSurveyResponse`.
- A safe deployed survey user or survey ID is still needed to generate a real
  active staging profile with `app.tools.survey_result_adapter`.
- Venue recommendations require map/place snapshot data. Beverage
  recommendations are the first Flutter target.
