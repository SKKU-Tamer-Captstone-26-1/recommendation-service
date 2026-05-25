# Load Test Plan

## Purpose

This document defines the Plan 010 load-test contract for measuring whether the
current recommendation architecture can support 500-5,000 user beta traffic.

Load tests are not a substitute for deployed smoke tests. Run deployed auth,
survey, map, recommendation, and chat smokes first.

## Scope

Covered gRPC calls:

- `GetProfileStatus`
- `GetBeverageRecommendations`
- `GetVenueRecommendations`
- `RecordRecommendationEvent`
- mixed read traffic

`RecordRecommendationEvent` mutates recommendation-owned interaction logs. It
must use safe staging test IDs and explicit mutation opt-in.

## Profiles

| Profile | RPS | Duration | Purpose |
|---|---:|---:|---|
| smoke | 1-5 | 5 minutes | connection and auth sanity |
| beta | 20 | 10 minutes | expected 1,000-5,000 user beta peak |
| peak | 50 | 10 minutes | realistic promotional peak |
| stress | 100 | 10 minutes | find current bottleneck |
| soak | expected peak | 1-2 hours | stability and pool/worker saturation |

## Commands

Run from repository root:

```bash
scripts/load/ghz-recommendation.sh profile
scripts/load/ghz-recommendation.sh beverage
scripts/load/ghz-recommendation.sh venue
scripts/load/ghz-recommendation.sh mixed
```

Set the target:

```bash
RECOMMENDATION_LOAD_GRPC_ADDR=<host:port>
SMOKE_AUTH_BEARER_TOKEN=<staging-token>
```

For TLS:

```bash
RECOMMENDATION_LOAD_TLS=1
```

## Pass Criteria

Initial beta target:

```text
beverage_recommendation_p95 <= 500ms
venue_recommendation_p95 <= 800ms
error_rate <= 1%
db_connection_saturation = false
qdrant_failure_count = 0
recommendation_empty_rate_spike = false
```

## Required Observability During Test

Collect:

- `ghz` output
- `/v1/operations/metrics` before and after
- DB connection/pool state
- Qdrant failure count
- sync lag
- recommendation empty rate
- application error logs with request IDs

## Result Storage

Store human-readable summaries under this directory using:

```text
docs/operations/load-tests/YYYY-MM-DD-<environment>-<profile>.md
```

Use `result-template.md`.

## Safety Rules

- Do not run stress or soak against production without approval.
- Do not run interaction load without safe test request/result IDs.
- Do not use real user JWTs for load tests.
- Do not disable auth to make load tests easier.
- Do not read survey-service or map-service databases to prepare load data.
