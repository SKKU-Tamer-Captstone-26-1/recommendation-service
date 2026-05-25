# Recommendation Load Test Harness

## Purpose

This folder contains operator-run load-test helpers for Plan 010.

The scripts target deployed or local `recommendation-service` gRPC endpoints.
They do not read or write survey-service or map-service databases.

## Tool

Install `ghz` before running:

```bash
ghz --version
```

## Safe Defaults

Read-only calls:

```bash
scripts/load/ghz-recommendation.sh profile
scripts/load/ghz-recommendation.sh beverage
scripts/load/ghz-recommendation.sh venue
```

Mutation call:

```bash
scripts/load/ghz-recommendation.sh interaction
```

`interaction` writes to `recommendation_interactions`. It is blocked unless all
of these are set:

```text
RECOMMENDATION_LOAD_ALLOW_MUTATION=1
RECOMMENDATION_LOAD_REQUEST_ID
RECOMMENDATION_LOAD_RESULT_ID
```

Use only safe staging test users and test recommendation IDs.

## Required Environment

```text
RECOMMENDATION_LOAD_GRPC_ADDR=localhost:50051
SMOKE_AUTH_BEARER_TOKEN=<jwt or internal smoke token>
```

For TLS endpoints:

```text
RECOMMENDATION_LOAD_TLS=1
```

For venue load:

```text
RECOMMENDATION_LOAD_SELECTED_BEVERAGE_ID=<uuid>
RECOMMENDATION_LOAD_LAT=37.5001
RECOMMENDATION_LOAD_LNG=127.0276
```

## Profiles

```text
RECOMMENDATION_LOAD_PROFILE=smoke   # 5 RPS, 5 minutes
RECOMMENDATION_LOAD_PROFILE=beta    # 20 RPS, 10 minutes
RECOMMENDATION_LOAD_PROFILE=peak    # 50 RPS, 10 minutes
RECOMMENDATION_LOAD_PROFILE=stress  # 100 RPS, 10 minutes
RECOMMENDATION_LOAD_PROFILE=soak    # 50 RPS, 2 hours by default
```

Override with:

```text
RECOMMENDATION_LOAD_RPS
RECOMMENDATION_LOAD_DURATION
```

## Examples

Smoke profile status:

```bash
RECOMMENDATION_LOAD_PROFILE=smoke \
  scripts/load/ghz-recommendation.sh profile
```

Beta beverage recommendation:

```bash
RECOMMENDATION_LOAD_PROFILE=beta \
  RECOMMENDATION_LOAD_GRPC_ADDR=localhost:50051 \
  scripts/load/ghz-recommendation.sh beverage
```

Peak mixed read-only load:

```bash
RECOMMENDATION_LOAD_PROFILE=peak \
  RECOMMENDATION_LOAD_SELECTED_BEVERAGE_ID=<uuid> \
  scripts/load/ghz-recommendation.sh mixed
```
