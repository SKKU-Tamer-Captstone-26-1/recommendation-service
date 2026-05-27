# Release Gate

## Purpose

This document defines the local release gate for moving
`recommendation-service` toward the 70% production-readiness target in
`docs/plans/009.md`.

The gate is intentionally deterministic. PostgreSQL remains canonical, Qdrant is
treated as rebuildable, and recommendation quality is checked with catalog audit
and offline drink evaluation thresholds.

## Local Gate

Run:

```bash
bash scripts/codex-harness/verify-release-gate.sh
```

The default gate runs:

- `pytest`
- `ruff`
- `compileall`
- `git diff --check`
- beverage catalog audit
- drink recommendation evaluation thresholds
- code boundary scan for direct survey/map database access

## Optional Database Smoke

When a local PostgreSQL database is running and `DATABASE_URL` points to it:

```bash
RUN_DB_SMOKE=1 bash scripts/codex-harness/verify-release-gate.sh
```

This additionally runs:

```bash
python3 -m alembic upgrade head
python3 -m app.tools.operational_metrics_smoke
```

The operational metrics smoke reads recommendation-owned PostgreSQL tables only.
It checks that the beta metrics surface includes request count, empty-result
rate, profile missing rate, sync lag, catalog audit failure count, and Qdrant
failure count.

## Optional Qdrant Rebuild Smoke

When PostgreSQL and Qdrant are both running:

```bash
RUN_DB_SMOKE=1 RUN_QDRANT_SMOKE=1 \
  bash scripts/codex-harness/verify-release-gate.sh
```

This additionally:

- imports/stages beverage candidates and promotes the reviewed MVP beverage seed
- re-runs seed promotion to prove idempotency
- audits active database beverages
- rebuilds the Qdrant beverage collection from PostgreSQL vectors
- runs a no-force Qdrant index pass to prove unchanged indexed points can skip
- queries Qdrant for an indexed beverage vector
- runs a beverage recommendation smoke proving serving still uses
  PostgreSQL-hydrated deterministic ranking after the Qdrant rebuild

## Optional Sync Smoke

When local PostgreSQL is running:

```bash
RUN_DB_SMOKE=1 RUN_SYNC_SMOKE=1 \
  bash scripts/codex-harness/verify-release-gate.sh
```

This additionally:

- imports/stages and promotes the reviewed MVP beverage seed
- runs the fake/protocol survey sync smoke through profile generation and
  beverage recommendation logging
- runs the map snapshot import and selected-beverage venue recommendation smoke
  with place, menu, inventory, and price revisions preserved in logs

## Optional Deployed Service Smoke

When deployed staging service URLs and credentials are available:

```bash
RUN_DEPLOYED_SMOKE=1 bash scripts/codex-harness/verify-release-gate.sh
```

This additionally runs:

```bash
python3 -m app.tools.deployed_smoke --mode all
```

Each smoke reads only service APIs or gRPC metadata. Missing endpoint or
credential environment variables cause that smoke to print `status=skipped`
instead of failing local development. A skipped deployed smoke is not production
evidence; it means the missing external input must stay tracked in
`docs/human-effort.md`.

Useful environment variables:

```text
AUTH_SMOKE_JWKS_URL
AUTH_SMOKE_EXPECTED_USER_ID
SURVEY_SMOKE_BASE_URL
SURVEY_SMOKE_GRPC_ADDR
SURVEY_SMOKE_EXTERNAL_USER_ID
SURVEY_SMOKE_RESPONSE_ID
SURVEY_SMOKE_EXPECTED_USER_ID
MAP_SMOKE_BASE_URL
RECOMMENDATION_SMOKE_GRPC_ADDR
RECOMMENDATION_SMOKE_HEALTH_ONLY
CHAT_SMOKE_HTTP_URL
CHAT_SMOKE_GRPC_ADDR
SMOKE_AUTH_BEARER_TOKEN
SMOKE_GRPC_TLS
```

If `SURVEY_SMOKE_GRPC_ADDR` is set, the survey deployed smoke checks gRPC
health. This confirms deployed protocol reachability only; it is not evidence
that the recommendation survey sync contract is deployed. Full survey sync
evidence still requires the event/response contract in
`docs/recommendation/sync-flow.md`.

If one of `SURVEY_SMOKE_EXTERNAL_USER_ID` or `SURVEY_SMOKE_RESPONSE_ID` is also
set, the survey gRPC smoke calls `GetSurveyResultByUser` or `GetSurveyResult`
and validates the returned `SurveyResult` through the recommendation mapper
adapter without writing a profile.

Set `SURVEY_SMOKE_EXPECTED_USER_ID` when the safe survey response must be proven
to belong to the same auth user used by the recommendation smoke.

If `RECOMMENDATION_SMOKE_HEALTH_ONLY=true` is set, the recommendation deployed
smoke checks gRPC health without requiring a user JWT. This confirms Cloud Run
gRPC reachability only; full profile and recommendation RPC evidence still
requires a safe auth-service JWT and active profile.

When a safe auth-service JWT and active profile exist, set
`RECOMMENDATION_SMOKE_EXPECT_ACTIVE_PROFILE=true`,
`RECOMMENDATION_SMOKE_RUN_BEVERAGE=true`, and
`RECOMMENDATION_SMOKE_RECORD_EVENT=true` to verify profile status, beverage
recommendations, and feedback recording in one deployed smoke.

If `AUTH_SMOKE_GRPC_ADDR` is set, the auth deployed smoke checks auth-service
gRPC `GetPublicKeys`. This confirms auth-service gRPC reachability and public
key availability without requiring recommendation-service to own JWT issuance.
When `SMOKE_AUTH_BEARER_TOKEN` and `AUTH_SMOKE_EXPECTED_USER_ID` are also set,
it validates that auth-service resolves the safe token to the expected user.

## Optional Cloud Run Deploy Gate

Before deploying the gRPC service, review:

```text
docs/operations/gcp-deployment.md
scripts/deploy/gcp-cloud-run-grpc.sh
```

The deploy script is intentionally guarded. It refuses database secrets that
appear to belong to auth, survey, chat, map, gateway, or a shared password-only
secret. A deploy is not production evidence until the dedicated
recommendation-owned PostgreSQL database, Qdrant endpoint, migrations, seed
promotion, Qdrant rebuild, and deployed recommendation smoke all pass.

Minimum syntax check:

```bash
bash -n scripts/deploy/gcp-cloud-run-grpc.sh
```

When staging secrets exist, run the non-deploying preflight:

```bash
RECOMMENDATION_DEPLOY_CHECK_ONLY=1 \
GCP_PROJECT=on-the-block-2026 \
RECOMMENDATION_DATABASE_SECRET=recommendation-db-dsn-staging \
RECOMMENDATION_QDRANT_URL_SECRET=recommendation-qdrant-url-staging \
bash scripts/deploy/gcp-cloud-run-grpc.sh
```

Before the first staging deployment, inspect the dedicated Cloud SQL plan:

```bash
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-provision-staging-sql.sh
```

Only run it with `RECOMMENDATION_PROVISION_APPLY=1` when creating billable
staging resources is approved.

Inspect the staging Qdrant plan:

```bash
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-provision-staging-qdrant.sh
```

Only run it with `RECOMMENDATION_QDRANT_PROVISION_APPLY=1` when creating a
temporary public Cloud Run Qdrant staging service protected by Qdrant API key is
approved.

Inspect runtime IAM before deploying jobs or services:

```bash
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-provision-staging-runtime-iam.sh
```

Only run it with `RECOMMENDATION_RUNTIME_IAM_APPLY=1` after the
recommendation-owned DB/Qdrant secrets exist.

Run staging release-prep jobs in order:

```bash
RECOMMENDATION_JOB_MODE=migrate GCP_PROJECT=on-the-block-2026 \
  bash scripts/deploy/gcp-run-staging-job.sh
RECOMMENDATION_JOB_MODE=seed GCP_PROJECT=on-the-block-2026 \
  bash scripts/deploy/gcp-run-staging-job.sh
RECOMMENDATION_JOB_MODE=catalog-audit GCP_PROJECT=on-the-block-2026 \
  bash scripts/deploy/gcp-run-staging-job.sh
RECOMMENDATION_JOB_MODE=qdrant-rebuild GCP_PROJECT=on-the-block-2026 \
  bash scripts/deploy/gcp-run-staging-job.sh
RECOMMENDATION_JOB_MODE=qdrant-smoke GCP_PROJECT=on-the-block-2026 \
  bash scripts/deploy/gcp-run-staging-job.sh
RECOMMENDATION_JOB_MODE=beverage-smoke GCP_PROJECT=on-the-block-2026 \
  bash scripts/deploy/gcp-run-staging-job.sh
```

## Operations Metrics Endpoint

The HTTP API exposes:

```text
GET /v1/operations/metrics
GET /v1/operations/metrics/prometheus
```

The response is intentionally flat and machine-readable for beta operations. It
includes persisted counts from recommendation-owned tables plus process-local
latency counters when the running process has served recommendation requests.

The endpoint does not read survey-service or map-service databases. Survey and
map health are represented only through recommendation-owned sync event tables,
dead letters, cursors, and map snapshot read-model state.

The Prometheus endpoint renders the same recommendation-owned operational state
plus process-local runtime latency histograms and gRPC status counters. It is
intended for staging/production scraping and must not block serving if scraping
fails.

## Rollback Notes

- Catalog rollback: restore the previous seed candidate list or deactivate newly
  promoted beverage rows.
- Qdrant rollback: disable Qdrant-backed retrieval and rebuild the collection
  from PostgreSQL vectors.
- Evaluation rollback: keep the stricter fixtures; lower thresholds only with an
  explicit product decision.

## Human-Required External Checks

The deployed survey-service and map-service smoke checks cannot be completed
until those deployed endpoints and auth metadata are available. Track that under
`docs/human-effort.md` if it blocks later plan slices.
