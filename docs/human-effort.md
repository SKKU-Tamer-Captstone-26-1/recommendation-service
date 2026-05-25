# Human Effort

## Purpose

This file records plan 009 work that cannot be completed from this repository
alone because it requires deployed external services, credentials, or production
policy decisions.

## Open Items

### Deployed Survey-Service Smoke

Status: external dependency required.

Current repo evidence:

- Fake/protocol survey sync smoke exists in `app.tools.survey_sync_smoke`.
- Local smoke can generate a derived profile and recommendation request log.
- `recommendation-service` does not read the survey database directly.

Human-provided inputs needed:

- deployed survey-service base URL or gRPC address
- auth metadata or internal service credential required for the smoke
- confirmation that the deployed event/response contract matches
  `docs/recommendation/sync-flow.md`
- a safe test survey response/event that may be read by recommendation-service

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

## Non-Blocking Operational Note

Local Qdrant smoke currently passes, but the local tool output warns that the
Python `qdrant-client` minor version is newer than the Docker Qdrant server
minor version. Align the production client/server versions before public launch.
