# Human Effort

## Purpose

This file records plan 009 and plan 010 work that cannot be completed from this
repository alone because it requires deployed external services, credentials, or
production policy decisions.

## Open Items

### Deployed Survey-Service Smoke

Status: partially unblocked; deployed gRPC health is reachable, but the
recommendation sync contract is not deployed yet.

Current repo evidence:

- Fake/protocol survey sync smoke exists in `app.tools.survey_sync_smoke`.
- Local smoke can generate a derived profile and recommendation request log.
- `recommendation-service` does not read the survey database directly.
- Deployed `survey-service` Cloud Run URL is
  `https://survey-service-vcuepibcwq-du.a.run.app`.
- gRPC health on `survey-service-vcuepibcwq-du.a.run.app:443` returns
  `SERVING`.
- gRPC reflection exposes `GetSurveyQuestions`, `SubmitSurvey`,
  `GetSurveyResult`, and `GetSurveyResultByUser`.
- HTTP survey smoke paths currently return Cloud Run `502 protocol error`.
- A controlled one-shot adapter exists for `GetSurveyResult` and
  `GetSurveyResultByUser` to generate a derived profile for a safe test user.
  This adapter is not production event sync because it has no cursor/event ID
  stream.

Human-provided inputs needed:

- safe deployed survey test user ID or survey ID allowed for adapter smoke
- auth metadata or internal service credential required for recommendation sync
- deployed survey-service recommendation sync contract:
  `ListSurveyEvents` and `GetSurveyResponse`
- a safe test survey event that may be read by recommendation-service after the
  sync contract exists
- confirmation that the deployed event/response contract matches
  `docs/recommendation/sync-flow.md`

Acceptance evidence when unblocked:

```text
survey_sync_deployed_smoke = pass
```

### Deployed Map-Service Snapshot Smoke

Status: external dependency required.

Current repo evidence:

- Map snapshot parser/importer exists for `map_snapshot_event_v1`.
- Local venue recommendation smoke preserves place, menu, inventory, and price
  revisions in recommendation logs.
- `recommendation-service` does not read or write map-service databases.

Human-provided inputs needed:

- deployed map-service/place-service base URL or gRPC address
- auth metadata or internal service credential required for the smoke
- confirmation that the deployed snapshot endpoint matches
  `docs/recommendation/map-read-model.md`
- a safe test snapshot event with place, menu, inventory, and price data for a
  known recommendation-owned beverage

Acceptance evidence when unblocked:

```text
map_snapshot_deployed_smoke = pass
```

### Auth-Service Production Metadata

Status: external confirmation required before production release.

Human-provided inputs needed:

- exact JWKS URL
- issuer and audience values
- whether the deployed gRPC endpoint is exposed over TLS on `:443`
- gateway metadata keys forwarded to recommendation-service

Acceptance evidence when unblocked:

```text
auth_context_smoke = pass
```

### Deployed Chat-Service Recommendation Smoke

Status: external dependency required.

Current repo evidence:

- The deployed smoke harness can call a configured chat HTTP smoke endpoint or
  gRPC health endpoint.
- The assistant/chat boundary requires chat-service to call
  recommendation-service for deterministic recommendation facts.

Human-provided inputs needed:

- deployed chat-service/assistant-service HTTP recommendation smoke URL or gRPC
  address
- auth metadata or internal service credential required for the smoke
- safe prompt/payload that asks for a recommendation and is allowed in staging
- expected response marker proving the answer used recommendation-service facts
  instead of ungrounded LLM ranking

Acceptance evidence when unblocked:

```text
chat_recommendation_deployed_smoke = pass
```

### Deployed Recommendation-Service Smoke

Status: external dependency required.

Current repo evidence:

- The deployed smoke harness can call a configured recommendation-service gRPC
  endpoint with bearer metadata.
- Local release gates prove deterministic beverage and venue recommendation
  behavior with recommendation-owned data and map snapshot read models.
- The smoke harness skips clearly when deployed endpoint and credential
  environment variables are not configured.

Human-provided inputs needed:

- deployed recommendation-service gRPC address
- TLS mode for the deployed gRPC endpoint
- auth metadata or internal service credential required for the smoke
- safe test user ID with an active derived profile
- optional safe selected beverage ID and location for venue recommendation smoke

Acceptance evidence when unblocked:

```text
recommendation_deployed_smoke = pass
```

## Non-Blocking Operational Note

Local Qdrant smoke currently passes, but the local tool output warns that the
Python `qdrant-client` minor version is newer than the Docker Qdrant server
minor version. Align the production client/server versions before public launch.
