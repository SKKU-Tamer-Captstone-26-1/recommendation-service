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
- The adapter now matches the deployed category-key survey contract and
  normalizes `cognac` to internal `brandy_cognac` plus the deployed `*_k`
  budget labels.
- The deployed smoke can verify a safe `SurveyResult` through the mapper without
  writing a profile, and can assert the survey user ID when
  `SURVEY_SMOKE_EXPECTED_USER_ID` is set.

Human-provided inputs needed:

- safe deployed survey test user ID or survey ID allowed for adapter smoke
- expected safe auth/survey user ID when validating by survey ID
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

Status: partially unblocked; deployed gRPC auth metadata can be checked, but a
safe auth JWT is still required for end-to-end recommendation RPC smoke.

Current repo evidence:

- Deployed auth-service Cloud Run URL is
  `https://authorization-service-vcuepibcwq-du.a.run.app`.
- HTTP `/.well-known/jwks.json` on the deployed auth-service returns gRPC
  `415 Content-Type is missing from the request`; deployed auth is gRPC-only for
  this integration path.
- gRPC reflection exposes `AuthService.GetPublicKeys` and
  `AuthService.ValidateToken`.
- recommendation-service now supports `AUTH_TOKEN_VALIDATION_MODE=grpc`, which
  calls auth-service `ValidateToken` instead of issuing or decoding tokens as a
  data owner.
- The auth deployed smoke can validate a safe token through `ValidateToken` and
  assert the resolved user when `AUTH_SMOKE_EXPECTED_USER_ID` is set.

Human-provided inputs needed:

- safe auth-service JWT for deployed recommendation smoke
- gateway metadata keys forwarded to recommendation-service

Acceptance evidence when unblocked:

```text
auth_public_keys_smoke = pass
auth_token_smoke = pending_safe_auth_jwt
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

### Recommendation GCP Deployment Resources

Status: external dependency required.

Current repo evidence:

- Cloud Run gRPC deployment script exists at
  `scripts/deploy/gcp-cloud-run-grpc.sh`.
- Staging Cloud SQL provisioning script exists at
  `scripts/deploy/gcp-provision-staging-sql.sh`.
- Staging Qdrant provisioning script exists at
  `scripts/deploy/gcp-provision-staging-qdrant.sh`.
- GCP deployment runbook exists at `docs/operations/gcp-deployment.md`.
- The deploy script refuses obvious shared-service database secrets.
- GCP inspection on 2026-05-27 found only these Secret Manager secrets:
  `DB_PASSWORD`, `GOOGLE_CLIENT_ID`, `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`, and
  `chat-db-dsn-staging`.
- GCP inspection on 2026-05-27 found only these Cloud SQL instances:
  `auth-postgres` and `ontheblock-chat-staging`.
- Non-deploying preflight with
  `RECOMMENDATION_DATABASE_SECRET=recommendation-db-dsn-staging` fails because
  the secret does not exist yet.
- Staging Cloud SQL provisioning dry-run on 2026-05-27 initially reported
  missing `recommendation-postgres-staging`, `recommendation_service`,
  `recommendation_user`, and `recommendation-db-dsn-staging`.
- First apply attempt failed because gcloud defaulted to Enterprise Plus, where
  `db-f1-micro` is not valid; the provisioning script now explicitly requests
  Cloud SQL Enterprise edition for the low-cost staging tier.
- Apply mode on 2026-05-27 created Cloud SQL instance
  `recommendation-postgres-staging`, database `recommendation_service`, user
  `recommendation_user`, and Secret Manager secret
  `recommendation-db-dsn-staging`.
- Post-create dry-run on 2026-05-27 reports the recommendation Cloud SQL
  instance, database, user, and secret all exist.
- Qdrant provisioning dry-run on 2026-05-27 reports missing service account,
  API key secret, Cloud Run service, and URL secret for staging Qdrant.
- Apply mode on 2026-05-27 created Cloud Run service
  `recommendation-qdrant-staging`, service account
  `recommendation-qdrant-staging`, and secrets
  `recommendation-qdrant-url-staging` and
  `recommendation-qdrant-api-key-staging`.
- Post-create dry-run on 2026-05-27 reports the Qdrant service account, API key
  secret, Cloud Run service, and URL secret all exist.
- Staging Qdrant HTTPS/API-key smoke passes with the application
  `qdrant-client` factory after the factory was fixed to stop forcing default
  port `6333` for full HTTPS URLs.
- The default staging/local Qdrant image is aligned to `qdrant/qdrant:v1.18.0`
  to match the Python `qdrant-client` minor version selected in the Cloud Run
  job image.
- Runtime IAM provisioning script exists at
  `scripts/deploy/gcp-provision-staging-runtime-iam.sh`.
- Runtime IAM dry-run on 2026-05-27 reports DB/Qdrant secrets exist and the
  recommendation runtime service account is missing.
- Apply mode on 2026-05-27 created
  `recommendation-service-staging@on-the-block-2026.iam.gserviceaccount.com`,
  granted `roles/cloudsql.client`, and granted Secret Manager access only to
  recommendation DB/Qdrant secrets.
- Post-create runtime IAM dry-run on 2026-05-27 reports the service account and
  DB/Qdrant secrets all exist.
- Recommendation Cloud Run deploy preflight now passes with recommendation-owned
  DB/Qdrant secrets and Cloud SQL connection configuration.
- Staging Cloud Run Job runner exists at
  `scripts/deploy/gcp-run-staging-job.sh` for migration, seed promotion,
  catalog audit, Qdrant rebuild, Qdrant smoke, and beverage recommendation
  smoke.
- Staging migration, seed promotion, catalog audit, Qdrant rebuild, Qdrant
  smoke, and beverage recommendation smoke passed on 2026-05-27.
- The remaining survey-side blocker is a safe deployed survey user or survey ID
  for `app.tools.survey_result_adapter`.
- Cloud Run service `recommendation-service` deployed on 2026-05-27 at
  `recommendation-service-vcuepibcwq-du.a.run.app:443`.
- Current serving revision is `recommendation-service-00003-b2d` at 100%
  traffic after applying mapper migration `0004_survey_mapper_v1_1` and
  enabling auth-service gRPC `ValidateToken`.
- Deployed gRPC health returns `SERVING`.
- Health-only deployed recommendation smoke passes with
  `RECOMMENDATION_SMOKE_HEALTH_ONLY=true`.
- `GetProfileStatus` without bearer metadata returns `UNAUTHENTICATED`.
- `GetProfileStatus` with an invalid bearer token returns `UNAUTHENTICATED`
  with auth-service reason `TOKEN_INVALID`.
- Flutter handoff is documented in `docs/api/flutter-handoff.md`.
- `scripts/deploy/gcp-run-plan-012-acceptance.sh` now runs the remaining Plan
  012 gates in order when a safe survey user/response, matching auth token, and
  explicit profile/event write opt-ins are provided.
- Health-only deployed auth, survey, and recommendation smokes pass with
  `SMOKE_GRPC_TIMEOUT_SECONDS=30`; the default runner timeout is set to 30s to
  tolerate Cloud Run cold starts.

Human-provided inputs needed:

- safe deployed survey test user ID or survey ID allowed for adapter smoke
- safe auth-service JWT for deployed recommendation smoke
- confirmation that the safe auth token resolves to the same user as the safe
  survey result
- Cloud Run ingress decision: private behind gateway or reviewed public staging
  smoke path

Acceptance evidence when unblocked:

```text
dedicated_recommendation_db = pass
database_secret_created = pass
qdrant_endpoint_configured = pass
cloud_run_revision_ready = pass
recommendation_deployed_smoke = pass
```

## Non-Blocking Operational Note

Qdrant remains staging-only and rebuildable from recommendation PostgreSQL. Move
from temporary Cloud Run Qdrant to Qdrant Cloud or another persistent managed
deployment before public production launch.
