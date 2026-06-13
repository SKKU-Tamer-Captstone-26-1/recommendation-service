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
- deployed survey mapper audit
- beverage catalog audit
- drink recommendation evaluation thresholds
- code boundary scan for direct survey/map database access

The deployed survey mapper audit is release evidence for survey-service
compatibility. It MUST keep `critical=0` before deployment. This verifies that
the current `ontheblock.survey.v1.SurveyResult` categories, category-specific
preference tokens, flavor keywords, and budget tokens all have deterministic
profile mapper coverage.

The beverage catalog audit is release evidence for app-visible drink cards. It
MUST keep `critical=0`, `image_url_coverage=1.0`, and
`image_license_metadata_coverage=1.0`, and `image_cache_metadata_coverage=1.0`
before deployment. This prevents active catalog items from reaching Flutter
without a display image URL, Korean alt text, source URL, original image URL,
cache key, license, attribution, display policy, and review status.

The catalog audit validates image metadata shape and source policy. It does not
perform network requests to third-party image hosts, because the deterministic
release gate must not depend on internet availability.

The drink recommendation evaluation MUST use the active beverage scoring config
version. As of Plan 020, the release gate validates `scoring_v3`; passing
fixtures against `scoring_v1` or `scoring_v2` alone is not release evidence for
deployed recommendation traffic.

The drink recommendation evaluation also MUST keep
`active_category_fixture_coverage=1.0` and
`minimum_fixtures_per_active_category >= 2`. This guarantees every active
beverage catalog category has multiple offline evaluation fixtures before the
service is released. The gate also requires at least 24 fixtures and
`top_k_hit_rate >= 0.95` for `scoring_v3`.

The evaluation MUST also prove the rank-one recommendation has usable
explanation evidence:

```text
top_result_reason_hit_rate = 1.0
average_top_result_reason_coverage >= 0.5
```

This prevents a release where the expected reason code appears somewhere in the
top five, but the first recommendation shown to Flutter or chatbot users lacks
any expected reason code.

The same evaluation MUST prove beverage follow-up diversity for chatbot/app
requests such as "다른 술 추천해줘":

```text
different_followup_change_rate = 1.0
different_followup_style_or_category_change_rate >= 0.95
adjacent_followup_change_rate = 1.0
```

The evaluation excludes the normal rank-one beverage and then reuses the same
deterministic diversity selection logic as the service. This prevents releases
where `DIFFERENT` or `ADJACENT` mode repeats the first recommendation across the
reviewed seed catalog and fixture profiles.

The evaluation MUST prove catalog price signals move beverage scores in the
expected direction:

```text
budget_affordable_candidate_count >= 20
budget_premium_candidate_count >= 2
budget_affordable_score_preference_rate = 1.0
budget_premium_score_preference_rate = 1.0
```

The budget sensitivity check keeps taste profile inputs the same and only
changes the survey budget from `under_30000` to `over_200000`. Affordable
catalog candidates must score higher for the low-budget variant, and premium
catalog candidates must score higher for the premium-tolerant variant. This is
not live venue price truth; it verifies the recommendation-owned catalog price
feature used by beverage scoring.

The evaluation MUST also prove reviewed positive candidates score higher than
reviewed negative candidates for every fixture:

```text
top_result_positive_hit_rate = 1.0
fixtures_missing_top_result_positive = []
positive_score_above_negative_rate = 1.0
positive_score_not_above_negative_failures = []
minimum_positive_negative_margin >= 0.15
```

This guards against two weak releases: one where the top five happen to contain
an acceptable item but the first card is not fixture-approved, and another where
the underlying score function no longer separates fixture-approved matches from
explicit counterexamples.

The evaluation MUST also prove taste-direction follow-up readiness before the
chatbot or gateway exposes a dedicated request field for prompts such as "더 달게",
"덜 피트하게", "더 가볍게", or "좀 더 허브/쌉쌀하게":

```text
directional_followup_count >= 6
directional_followup_score_preference_rate = 1.0
directional_followup_direction_count >= 6
minimum_directional_followup_margin >= 0.05
```

Directional follow-up fixtures create deterministic profile variants from the
same deployed survey mapper and then score the reviewed catalog with the normal
beverage scoring function. For each declared direction, fixture-approved
positive candidates must score higher than explicit negative counterexamples.
This is not a live API contract yet; it is release evidence that the catalog,
mapper, and scoring model can support future chatbot follow-up controls without
letting chatbot-service invent or rerank beverages.

The same evaluation must cover deployed survey scenarios:

```text
experience_level_fixture_coverage = 1.0
minimum_fixtures_per_experience_level >= 3
deployed_budget_range_fixture_coverage = 1.0
minimum_fixtures_per_deployed_budget_range >= 1
deployed_survey_category_fixture_coverage = 1.0
deployed_survey_category_trait_fixture_coverage = 1.0
deployed_survey_flavor_keyword_fixture_coverage = 1.0
```

This prevents releases that only work for one user experience level or that miss
budget bands emitted by the deployed survey-service contract. The deployed
survey token coverage checks are stronger than the mapper audit: they require
the offline drink recommendation fixtures to include the current deployed
category tokens, category-style tokens, and flavor keywords, then pass normal
recommendation scoring thresholds.

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

## Optional Beverage Image URL Smoke

Before a release where Flutter will display beverage images, operators may run a
network-dependent smoke check against the seed catalog:

```bash
python3 -m app.tools.beverage_image_url_smoke \
  --report /private/tmp/recommendation-release-gate/beverage_image_url_smoke.json
```

When a local or staging recommendation-owned PostgreSQL database is running and
`DATABASE_URL` points to it, check the promoted active catalog instead:

```bash
python3 -m app.tools.beverage_image_url_smoke \
  --database \
  --report /private/tmp/recommendation-release-gate/beverage_image_url_smoke_db.json
```

By default, the CLI de-duplicates repeated image URLs and waits briefly between
requests. This matters because many MVP beverages share a category fallback
image, and third-party hosts may rate-limit repeated checks. Use
`--include-duplicate-urls` only when every beverage-to-image mapping must be
reported separately.

This smoke sends `HEAD` requests and falls back to `GET` for hosts that do not
serve metadata through `HEAD`. A URL passes only when it returns a 2xx/3xx
status and an `image/*` content type. The smoke sends an explicit
`ONTHEBLOCK-recommendation-service` User-Agent so third-party hosts do not treat
the check as an anonymous default HTTP client. This is optional release evidence
because external hosts can fail independently of recommendation-service.

## Optional Beverage Image Cache Export

Before using `BEVERAGE_IMAGE_CDN_BASE_URL` in staging or production, generate an
image cache manifest from the reviewed beverage seed:

```bash
python3 -m app.tools.beverage_image_cache_export \
  --output-dir /private/tmp/recommendation-beverage-image-cache \
  --manifest /private/tmp/recommendation-beverage-image-cache/manifest.json \
  --gcs-bucket ontheblock-beverage-images-staging
```

This default mode is manifest-only and does not download binary images. It
records each cache key, original licensed image URL, source/license page,
attribution, connected beverage catalog keys, and target GCS URI.

When operators are ready to mirror the licensed images locally before uploading
to GCS, run:

```bash
python3 -m app.tools.beverage_image_cache_export \
  --download \
  --output-dir /private/tmp/recommendation-beverage-image-cache \
  --manifest /private/tmp/recommendation-beverage-image-cache/manifest.json \
  --gcs-bucket ontheblock-beverage-images-staging
```

Then upload the generated object tree:

```bash
gcloud storage cp -r \
  /private/tmp/recommendation-beverage-image-cache/beverage-images \
  gs://ontheblock-beverage-images-staging/
```

After the bucket/CDN URL is ready, set `BEVERAGE_IMAGE_CDN_BASE_URL` and re-run
seed promotion. The app display URL becomes the ONTHEBLOCK-managed CDN URL,
while `metadata_json.image.original_image_url`, `source_url`, `license`, and
`attribution` keep source traceability.

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
MAP_ROUTE_SMOKE_BASE_URL
MAP_ROUTE_SMOKE_PATH
MAP_ROUTE_SMOKE_PLACE_ID
MAP_ROUTE_SMOKE_ORIGIN_LAT
MAP_ROUTE_SMOKE_ORIGIN_LNG
MAP_ROUTE_SMOKE_DESTINATION_LAT
MAP_ROUTE_SMOKE_DESTINATION_LNG
MAP_ROUTE_SMOKE_EXPECT_ROUTE
MAP_ROUTE_SMOKE_SERVERLESS_AUTH_TOKEN
RECOMMENDATION_SMOKE_GRPC_ADDR
RECOMMENDATION_SMOKE_HEALTH_ONLY
RECOMMENDATION_SMOKE_RUN_BEVERAGE
RECOMMENDATION_SMOKE_EXPECT_BEVERAGE_RESULTS
RECOMMENDATION_SMOKE_VALIDATE_BEVERAGE_CONTRACT
RECOMMENDATION_SMOKE_REQUIRE_IMAGE_METADATA
RECOMMENDATION_SMOKE_REQUIRE_BUDGET_TRADEOFF
RECOMMENDATION_SMOKE_SELECTED_BEVERAGE_ID
RECOMMENDATION_SMOKE_VENUE_PLACE_TYPES
RECOMMENDATION_SMOKE_EXPECT_VENUE_PLACE_TYPES
RECOMMENDATION_SMOKE_EXPECT_VENUE_RESULTS
RECOMMENDATION_SMOKE_VALIDATE_VENUE_CONTRACT
RECOMMENDATION_SMOKE_EXPECT_ROUTE_DISTANCE
RECOMMENDATION_SMOKE_DIVERSITY_MODE
RECOMMENDATION_SMOKE_FLAVOR_DIRECTION
RECOMMENDATION_SMOKE_SERVERLESS_AUTH_TOKEN
RECOMMENDATION_SMOKE_SERVERLESS_AUTH_HEADER
CHAT_SMOKE_HTTP_URL
CHAT_SMOKE_GRPC_ADDR
SMOKE_AUTH_BEARER_TOKEN
SMOKE_SERVERLESS_AUTH_TOKEN
SMOKE_GRPC_TLS
SMOKE_GRPC_TIMEOUT_SECONDS
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

If `MAP_ROUTE_SMOKE_BASE_URL` or `MAP_SMOKE_BASE_URL` is set with route
coordinates, the `map_route` deployed smoke posts the route-distance contract
used by recommendation-service:

```text
POST /internal/v1/recommendation/route-distance
contract_version = map_route_distance_request_v1
```

By default, `204` or `404` is accepted as "no route estimate" because some
fixtures may not be routable yet. Set `MAP_ROUTE_SMOKE_EXPECT_ROUTE=true` when
the chosen smoke coordinates must produce a route distance. If map-service is
private on Cloud Run, pass the serverless token as
`MAP_ROUTE_SMOKE_SERVERLESS_AUTH_TOKEN` or `SMOKE_SERVERLESS_AUTH_TOKEN`; the
smoke sends it as `x-serverless-authorization`.

If `recommendation-service` is private at the Cloud Run IAM layer, also set
`SMOKE_SERVERLESS_AUTH_TOKEN` or
`RECOMMENDATION_SMOKE_SERVERLESS_AUTH_TOKEN`. The smoke sends this value as:

```text
x-serverless-authorization: Bearer <google-id-token>
```

This verifies the production metadata split expected from app-gateway:

```text
authorization = auth-service user token
x-serverless-authorization = Cloud Run IAM token
```

When a safe auth-service JWT and active profile exist, set
`RECOMMENDATION_SMOKE_EXPECT_ACTIVE_PROFILE=true`,
`RECOMMENDATION_SMOKE_RUN_BEVERAGE=true`, and
`RECOMMENDATION_SMOKE_RECORD_EVENT=true` to verify profile status, beverage
recommendations, and feedback recording in one deployed smoke.

For stronger deployed beverage API evidence, also set:

```text
RECOMMENDATION_SMOKE_EXPECT_BEVERAGE_RESULTS=true
RECOMMENDATION_SMOKE_VALIDATE_BEVERAGE_CONTRACT=true
RECOMMENDATION_SMOKE_REQUIRE_IMAGE_METADATA=true
RECOMMENDATION_SMOKE_REQUIRE_BUDGET_TRADEOFF=true
```

This verifies that deployed `GetBeverageRecommendations` returns sequential
ranks, ids, display names, category, finite scores, reason codes, explanations,
score breakdown metadata, `metadata.source`, optional image metadata, and
optional budget trade-off metadata. It is the deployed counterpart to the local
catalog audit and Flutter handoff contract.

Set `RECOMMENDATION_SMOKE_FLAVOR_DIRECTION` to values such as `SMOKIER`,
`LIGHTER`, or `BEVERAGE_FLAVOR_DIRECTION_MORE_HERBAL_BITTER` when the deployed
smoke should prove the flavor follow-up enum is accepted over gRPC. Set
`RECOMMENDATION_SMOKE_DIVERSITY_MODE` to `DIFFERENT` or `ADJACENT` when the
smoke should verify follow-up diversity request wiring.

For stronger deployed venue API evidence, set a safe canonical beverage id and
enable the venue contract validator:

```text
RECOMMENDATION_SMOKE_SELECTED_BEVERAGE_ID=<safe-beverage-uuid>
RECOMMENDATION_SMOKE_EXPECT_VENUE_RESULTS=true
RECOMMENDATION_SMOKE_VALIDATE_VENUE_CONTRACT=true
```

This verifies that deployed `GetVenueRecommendations` returns sequential ranks,
ids, place fields, finite scores, reason codes, explanations, score breakdown
metadata, and `metadata.source` distance metadata. The validator checks
`distance_strategy`, `distance_source`, `distance_confidence`,
`is_route_distance`, `distance_fallback_used`, straight-line distance, and route
distance fields when present.

To prove the deployed venue place-type request contract, also set:

```text
RECOMMENDATION_SMOKE_VENUE_PLACE_TYPES=store
```

The smoke sends this value through `GetVenueRecommendations.place_types` and,
when `RECOMMENDATION_SMOKE_VALIDATE_VENUE_CONTRACT=true`, verifies that every
returned result has an allowed snapshot `place_type`. Friendly request aliases
are resolved in the smoke the same way as the API contract:

```text
store/shop -> bottle_shop, liquor_shop, store
bar -> bar, cocktail_bar, pub, whiskey_bar, wine_bar
outdoor -> outdoor_spot, outdoor
```

Set `RECOMMENDATION_SMOKE_EXPECT_VENUE_PLACE_TYPES` when the expected response
type should be stricter than the request alias, for example
`RECOMMENDATION_SMOKE_EXPECT_VENUE_PLACE_TYPES=liquor_shop`.

Set `RECOMMENDATION_SMOKE_EXPECT_ROUTE_DISTANCE=true` only when the chosen
staging fixture is expected to produce at least one map-service route-distance
result. If this flag is enabled and every result falls back to
`straight_line_mvp`, the smoke fails. This protects Flutter/chatbot copy from
claiming route-style distance before the deployed route provider is actually
working.

## Drink Recommendation Margin Gate

The drink evaluation release gate checks more than top-k hit rate. Reviewed
positive catalog candidates must score above explicit negative counterexamples
with a minimum margin:

```text
minimum_positive_negative_margin >= 0.15
minimum_directional_followup_margin >= 0.05
```

This keeps the deterministic scorer from passing release with fragile
near-ties. The directional threshold is lower on purpose because follow-up
requests such as "smokier" or "less sweet" can be subtle inside one beverage
category.

The drink evaluation fixture set currently contains at least 29 fixtures. Five
fixtures use the deployed survey-service token vocabulary directly so the
release gate covers:

```text
deployed survey categories: whiskey, wine, cognac, cocktail, beer
deployed category-style tokens: 20 / 20 covered
deployed flavor keywords: 9 / 9 covered
```

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

Inspect the staging beverage image cache plan:

```bash
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-provision-staging-image-cache.sh
```

Only run it with `RECOMMENDATION_IMAGE_CACHE_PROVISION_APPLY=1` when creating a
recommendation-owned image cache bucket and CDN base URL secret is approved.
Set `RECOMMENDATION_IMAGE_CACHE_PUBLIC_READ=1` only when the bucket URL is the
reviewed public MVP display URL.

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

When the beverage image cache secret exists and reviewed images have been
uploaded, run the seed job with:

```bash
RECOMMENDATION_JOB_MODE=seed \
RECOMMENDATION_BEVERAGE_IMAGE_CDN_BASE_URL_SECRET=recommendation-beverage-image-cdn-base-url-staging \
GCP_PROJECT=on-the-block-2026 \
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
