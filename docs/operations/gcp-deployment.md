# GCP Deployment

## Purpose

This runbook defines the guarded staging deployment path for
`recommendation-service` on Cloud Run.

It only authorizes recommendation-owned resources. It does not authorize using
auth, survey, chat, map, gateway, or shared databases for recommendation state.

## Boundary Rules

Deployment must preserve these ownership rules:

| Resource | Owner | Rule |
|---|---|---|
| Raw survey answers | `survey-service` | Read only through survey-service gRPC/API |
| Derived profiles | `recommendation-service` | Store in recommendation PostgreSQL |
| Beverage catalog and vectors | `recommendation-service` | PostgreSQL canonical, Qdrant rebuildable |
| Auth/JWTs | `auth-service` | Verify metadata only |
| Places, menus, inventory, prices | map/place service | Consume snapshots only |

Forbidden deployment shortcuts:

```text
recommendation-service -> auth DB
recommendation-service -> chat DB
recommendation-service -> survey DB
recommendation-service -> map/place DB
```

## Required Staging Resources

Before deploying, create or confirm:

```text
Cloud SQL instance: recommendation-postgres-staging
PostgreSQL database: recommendation_service
PostgreSQL user: recommendation_user
Secret Manager secret: recommendation-db-dsn-staging
Qdrant endpoint: recommendation-owned staging Qdrant
Secret Manager secret: recommendation-qdrant-url-staging
Secret Manager secret: recommendation-qdrant-api-key-staging when required
Cloud Storage bucket: recommendation-owned beverage image cache bucket
Secret Manager secret: recommendation-beverage-image-cdn-base-url-staging
```

The `DATABASE_URL` secret must point only at the recommendation-owned database.
Do not reuse `DB_PASSWORD`, `chat-db-dsn-staging`, auth-service credentials, or
any service-owned database secret from another repo.

The Cloud Run runtime service account must have Secret Manager access only for
the recommendation-owned secrets it needs. Do not grant broad access to other
service secrets.

## Provision Staging PostgreSQL

Dry-run inspection:

```bash
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-provision-staging-sql.sh
```

Apply:

```bash
RECOMMENDATION_PROVISION_APPLY=1 \
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-provision-staging-sql.sh
```

The script creates or confirms:

```text
instance = recommendation-postgres-staging
edition = ENTERPRISE
database = recommendation_service
user = recommendation_user
secret = recommendation-db-dsn-staging
connection_name = on-the-block-2026:asia-northeast3:recommendation-postgres-staging
```

The secret stores a Cloud Run Cloud SQL connector DSN:

```text
postgresql+psycopg://recommendation_user:<password>@/recommendation_service?host=/cloudsql/<connection-name>
```

The staging user receives `cloudsqlsuperuser` by default because the foundation
migration creates PostgreSQL extensions. Google Cloud documents that Cloud SQL
PostgreSQL extensions can only be created by users in the `cloudsqlsuperuser`
role, and PostGIS is supported for PostgreSQL 16:

```text
https://cloud.google.com/sql/docs/postgres/extensions
```

Production hardening follow-up:

```text
Create a separate migration owner and runtime app user before public launch.
The runtime app user should not keep extension-creation privileges.
```

## Provision Staging Qdrant

Preferred production direction is Qdrant Cloud in the same region. For this
staging plan, a temporary Cloud Run Qdrant service is acceptable because Qdrant
is rebuildable from recommendation PostgreSQL.

Dry-run inspection:

```bash
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-provision-staging-qdrant.sh
```

Apply:

```bash
RECOMMENDATION_QDRANT_PROVISION_APPLY=1 \
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-provision-staging-qdrant.sh
```

The script creates or confirms:

```text
service = recommendation-qdrant-staging
image = docker.io/qdrant/qdrant:v1.18.0
api_key_secret = recommendation-qdrant-api-key-staging
url_secret = recommendation-qdrant-url-staging
service_account = recommendation-qdrant-staging
storage_policy = ephemeral_rebuild_from_postgresql
```

The Cloud Run Qdrant service is public at the Cloud Run ingress layer but
protected by Qdrant's API key. Qdrant documents
`QDRANT__SERVICE__API_KEY` as the environment variable for API key
configuration and recommends TLS when API keys are used:

```text
https://qdrant.tech/documentation/guides/security/
```

Rollback:

```text
Delete the staging Qdrant service and secrets only after PostgreSQL has the
canonical vectors. Rebuild Qdrant from PostgreSQL after recreation.
```

## Provision Runtime IAM

Dry-run inspection:

```bash
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-provision-staging-runtime-iam.sh
```

Apply:

```bash
RECOMMENDATION_RUNTIME_IAM_APPLY=1 \
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-provision-staging-runtime-iam.sh
```

The script creates or confirms:

```text
service_account = recommendation-service-staging@on-the-block-2026.iam.gserviceaccount.com
project_role = roles/cloudsql.client
secret_access = recommendation-db-dsn-staging
secret_access = recommendation-qdrant-url-staging
secret_access = recommendation-qdrant-api-key-staging
```

Do not grant this service account access to auth, survey, chat, map, gateway,
or shared database secrets.

## Provision Beverage Image Cache

The beverage image cache is display infrastructure for recommendation-owned
beverage catalog metadata. It is not recommendation scoring evidence and must
not store survey, user, map, inventory, or price data.

Dry-run inspection:

```bash
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-provision-staging-image-cache.sh
```

Apply:

```bash
RECOMMENDATION_IMAGE_CACHE_PROVISION_APPLY=1 \
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-provision-staging-image-cache.sh
```

The script creates or confirms:

```text
bucket = ontheblock-beverage-images-staging-<project>
location = asia-northeast3
cdn_base_url_secret = recommendation-beverage-image-cdn-base-url-staging
secret_access = recommendation-service-staging runtime service account
```

By default, the script does not grant public read. Set
`RECOMMENDATION_IMAGE_CACHE_PUBLIC_READ=1` only when the bucket URL is the
reviewed public MVP image URL. If a separate CDN host is used, set:

```text
RECOMMENDATION_IMAGE_CDN_BASE_URL=https://<image-cdn-host>
```

Then export and upload reviewed image assets:

```bash
python3 -m app.tools.beverage_image_cache_export \
  --download \
  --output-dir /private/tmp/recommendation-beverage-image-cache \
  --manifest /private/tmp/recommendation-beverage-image-cache/manifest.json \
  --gcs-bucket ontheblock-beverage-images-staging-<project>

gcloud storage cp -r \
  /private/tmp/recommendation-beverage-image-cache/beverage-images \
  gs://ontheblock-beverage-images-staging-<project>/
```

For the seed job to use the CDN base URL secret, pass:

```bash
RECOMMENDATION_JOB_MODE=seed \
RECOMMENDATION_BEVERAGE_IMAGE_CDN_BASE_URL_SECRET=recommendation-beverage-image-cdn-base-url-staging \
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-run-staging-job.sh
```

## Deploy gRPC Service

Preflight without deploying:

```bash
RECOMMENDATION_DEPLOY_CHECK_ONLY=1 \
GCP_PROJECT=on-the-block-2026 \
GCP_REGION=asia-northeast3 \
RECOMMENDATION_DATABASE_SECRET=recommendation-db-dsn-staging \
RECOMMENDATION_QDRANT_URL_SECRET=recommendation-qdrant-url-staging \
RECOMMENDATION_QDRANT_API_KEY_SECRET=recommendation-qdrant-api-key-staging \
RECOMMENDATION_CLOUD_SQL_INSTANCE=on-the-block-2026:asia-northeast3:recommendation-postgres-staging \
bash scripts/deploy/gcp-cloud-run-grpc.sh
```

Default command:

```bash
GCP_PROJECT=on-the-block-2026 \
GCP_REGION=asia-northeast3 \
RECOMMENDATION_DATABASE_SECRET=recommendation-db-dsn-staging \
RECOMMENDATION_QDRANT_URL_SECRET=recommendation-qdrant-url-staging \
RECOMMENDATION_QDRANT_API_KEY_SECRET=recommendation-qdrant-api-key-staging \
RECOMMENDATION_CLOUD_SQL_INSTANCE=on-the-block-2026:asia-northeast3:recommendation-postgres-staging \
bash scripts/deploy/gcp-cloud-run-grpc.sh
```

The script deploys:

```text
service = recommendation-service
entrypoint = python -m app.grpc.main
port = 8080
protocol = Cloud Run HTTP/2 for gRPC
```

Runtime environment:

```text
APP_ENV=staging
GRPC_HOST=0.0.0.0
GRPC_PORT=8080
AUTH_SERVICE_URL=https://authorization-service-vcuepibcwq-du.a.run.app
AUTH_JWKS_URL=https://authorization-service-vcuepibcwq-du.a.run.app/.well-known/jwks.json
AUTH_SERVICE_GRPC_ADDR=authorization-service-vcuepibcwq-du.a.run.app:443
AUTH_SERVICE_GRPC_TLS=true
AUTH_TOKEN_VALIDATION_MODE=grpc
JWT_ISSUER=on-the-block-auth
JWT_AUDIENCE=recommendation-service
SURVEY_SERVICE_URL=https://survey-service-vcuepibcwq-du.a.run.app
SURVEY_SERVICE_GRPC_ADDR=survey-service-vcuepibcwq-du.a.run.app:443
MAP_ROUTE_DISTANCE_ENABLED=false
MAP_ROUTE_DISTANCE_FALLBACK_ENABLED=true
SYNC_WORKER_ENABLED=false
```

Runtime service account:

```text
recommendation-service-staging@on-the-block-2026.iam.gserviceaccount.com
```

`SYNC_WORKER_ENABLED=false` is intentional for this deployment slice because
the deployed survey-service does not yet expose the cursor-based production sync
contract. Use the controlled survey result adapter for safe staging profile
generation until that contract exists.

By default, the script deploys with:

```text
--no-allow-unauthenticated
```

Production mobile traffic must stay behind `app-gateway-service`:

```text
Flutter -> app-gateway-service -> private recommendation-service
```

Grant the app-gateway runtime service account Cloud Run Invoker on
`recommendation-service`:

```bash
gcloud run services add-iam-policy-binding recommendation-service \
  --region=asia-northeast3 \
  --project=on-the-block-2026 \
  --member="serviceAccount:<APP_GATEWAY_SERVICE_ACCOUNT>" \
  --role=roles/run.invoker
```

When app-gateway calls the private recommendation gRPC service, it must send:

```text
authorization: Bearer <auth-service-jwt>
x-serverless-authorization: Bearer <google-id-token-for-recommendation-service>
```

The first token is for application user context. The second token is for Cloud
Run IAM admission. Do not replace the user token with the Google ID token.

Set:

```bash
RECOMMENDATION_ALLOW_UNAUTHENTICATED=1
```

only for a reviewed staging path where Cloud Run ingress is public but the
recommendation gRPC service still verifies bearer auth metadata.

## Migrate, Seed, and Rebuild

After the dedicated database, Qdrant, and runtime IAM exist, run these Cloud Run
Jobs before serving Flutter traffic:

```bash
RECOMMENDATION_JOB_MODE=migrate \
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-run-staging-job.sh

RECOMMENDATION_JOB_MODE=seed \
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-run-staging-job.sh

RECOMMENDATION_JOB_MODE=catalog-audit \
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-run-staging-job.sh

RECOMMENDATION_JOB_MODE=qdrant-rebuild \
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-run-staging-job.sh

RECOMMENDATION_JOB_MODE=qdrant-smoke \
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-run-staging-job.sh

RECOMMENDATION_JOB_MODE=beverage-smoke \
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-run-staging-job.sh
```

The jobs use the Cloud SQL connector and Secret Manager injection. Do not paste
real DSNs into committed files.

When a safe deployed survey user or survey response is available, generate the
staging profile through the deployed survey adapter:

```bash
RECOMMENDATION_JOB_MODE=survey-adapter-user \
RECOMMENDATION_SURVEY_ADAPTER_EXTERNAL_USER_ID=<safe-user-id> \
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-run-staging-job.sh
```

or:

```bash
RECOMMENDATION_JOB_MODE=survey-adapter-response \
RECOMMENDATION_SURVEY_ADAPTER_RESPONSE_ID=<safe-survey-id> \
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-run-staging-job.sh
```

Set:

```text
RECOMMENDATION_SURVEY_ADAPTER_DRY_RUN=1
```

to validate mapping without writing a profile. If survey-service requires a
bearer credential, store it in a recommendation-owned secret and set:

```text
SURVEY_SERVICE_GRPC_AUTH_BEARER_TOKEN_SECRET=recommendation-survey-grpc-token-staging
```

## Survey Adapter Smoke

When a safe deployed survey user or survey ID is available:

First validate the deployed survey result contract without writing a profile:

```bash
SURVEY_SMOKE_GRPC_ADDR=survey-service-vcuepibcwq-du.a.run.app:443 \
SURVEY_SMOKE_EXTERNAL_USER_ID=<safe-user-id> \
SMOKE_GRPC_TLS=1 \
python3 -m app.tools.deployed_smoke --mode survey
```

Use `SURVEY_SMOKE_RESPONSE_ID=<safe-survey-id>` instead of
`SURVEY_SMOKE_EXTERNAL_USER_ID` when validating by survey response ID.

```bash
SURVEY_SERVICE_GRPC_ADDR=survey-service-vcuepibcwq-du.a.run.app:443 \
SURVEY_SERVICE_GRPC_AUTH_BEARER_TOKEN=<token-if-required> \
DATABASE_URL=<recommendation-owned-dsn> \
python3 -m app.tools.survey_result_adapter \
  --external-user-id <safe-user-id>
```

This creates a derived recommendation profile from the deployed survey result.
It is staging-only and does not replace cursor-based production sync. The
adapter uses `survey_mapper_v1_1`, which normalizes deployed category-key
answers such as `cognac` and `over_200k` into the recommendation-owned mapper
shape.

## Deployed Smoke

After Cloud Run reports a ready revision:

```bash
RECOMMENDATION_SMOKE_GRPC_ADDR=recommendation-service-vcuepibcwq-du.a.run.app:443 \
SMOKE_AUTH_BEARER_TOKEN=<safe-staging-token> \
SMOKE_SERVERLESS_AUTH_TOKEN=<google-id-token-for-recommendation-service> \
SMOKE_GRPC_TLS=1 \
python3 -m app.tools.deployed_smoke --mode recommendation
```

For a stronger active-profile smoke:

```bash
RECOMMENDATION_SMOKE_GRPC_ADDR=<recommendation-cloud-run-host>:443 \
SMOKE_AUTH_BEARER_TOKEN=<safe-staging-token> \
SMOKE_SERVERLESS_AUTH_TOKEN=<google-id-token-for-recommendation-service> \
RECOMMENDATION_SMOKE_EXPECT_ACTIVE_PROFILE=true \
RECOMMENDATION_SMOKE_RUN_BEVERAGE=true \
RECOMMENDATION_SMOKE_RECORD_EVENT=true \
SMOKE_GRPC_TLS=1 \
python3 -m app.tools.deployed_smoke --mode recommendation
```

`RECOMMENDATION_SMOKE_RECORD_EVENT=true` records an impression for the first
beverage result using allowlisted smoke metadata. This completes the staging
Flutter call sequence through `RecordRecommendationEvent`.

For selected-beverage venue smoke with a place-type filter:

```bash
RECOMMENDATION_SMOKE_GRPC_ADDR=<recommendation-cloud-run-host>:443 \
SMOKE_AUTH_BEARER_TOKEN=<safe-staging-token> \
SMOKE_SERVERLESS_AUTH_TOKEN=<google-id-token-for-recommendation-service> \
RECOMMENDATION_SMOKE_SELECTED_BEVERAGE_ID=<safe-beverage-uuid> \
RECOMMENDATION_SMOKE_LAT=37.5 \
RECOMMENDATION_SMOKE_LNG=127.0 \
RECOMMENDATION_SMOKE_VENUE_PLACE_TYPES=store \
RECOMMENDATION_SMOKE_EXPECT_VENUE_RESULTS=true \
RECOMMENDATION_SMOKE_VALIDATE_VENUE_CONTRACT=true \
SMOKE_GRPC_TLS=1 \
python3 -m app.tools.deployed_smoke --mode recommendation
```

This verifies that deployed `GetVenueRecommendations` accepts the same
`place_types` contract used by Flutter, app-gateway-service, and chatbot-service
for store/bar/outdoor venue intent. It still uses recommendation read-model
snapshots only; canonical place data remains owned by map-service.

For private Cloud Run smoke from a shell with `gcloud` credentials, generate
the serverless token outside the tool and pass it through the environment:

```bash
SMOKE_SERVERLESS_AUTH_TOKEN="$(gcloud auth print-identity-token)" \
RECOMMENDATION_SMOKE_GRPC_ADDR=recommendation-service-vcuepibcwq-du.a.run.app:443 \
SMOKE_AUTH_BEARER_TOKEN=<safe-staging-token> \
SMOKE_GRPC_TLS=1 \
python3 -m app.tools.deployed_smoke --mode recommendation
```

If the shell account cannot mint the correct audience token, run the smoke from
an environment that uses the app-gateway runtime service account or use
`grpcurl` with the service account's Google ID token.

## Plan 012 Acceptance Runner

Use the guarded runner when the safe survey user, matching safe auth token, and
write approval are available:

```bash
PLAN012_SAFE_SURVEY_EXTERNAL_USER_ID=<safe-user-id> \
SMOKE_AUTH_BEARER_TOKEN=<safe-staging-token-for-same-user> \
SMOKE_GRPC_TIMEOUT_SECONDS=30 \
PLAN012_ALLOW_PROFILE_WRITE=1 \
PLAN012_ALLOW_EVENT_WRITE=1 \
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-run-plan-012-acceptance.sh
```

Use `PLAN012_SAFE_SURVEY_RESPONSE_ID=<safe-survey-id>` instead of
`PLAN012_SAFE_SURVEY_EXTERNAL_USER_ID` when validating by survey response ID.
In that mode, also set `PLAN012_EXPECTED_EXTERNAL_USER_ID=<safe-user-id>` so
the runner can prove the auth token and survey result belong to the same safe
user.

The runner performs:

```text
1. auth-service gRPC GetPublicKeys and ValidateToken user check
2. survey-service gRPC health plus SurveyResult mapper contract check
3. staging survey adapter Cloud Run Job to generate the derived profile
4. deployed recommendation GetProfileStatus, GetBeverageRecommendations, and
   RecordRecommendationEvent
```

Set `PLAN012_PROFILE_ALREADY_ACTIVE=1` only when the profile was already
generated through the deployed survey adapter and should not be written again.
The script defaults `SMOKE_GRPC_TIMEOUT_SECONDS` to `30` because deployed Cloud
Run gRPC services may cold start slowly.

Current deployed evidence:

```text
revision = recommendation-service-00003-b2d
traffic = 100%
grpc_host = recommendation-service-vcuepibcwq-du.a.run.app:443
grpc_health = SERVING
health_only_deployed_smoke_timeout = 30s
health_only_deployed_smoke = pass
GetProfileStatus without bearer token = UNAUTHENTICATED
GetProfileStatus with invalid bearer token = UNAUTHENTICATED TOKEN_INVALID
latest_migration = 0004_survey_mapper_v1_1
auth_validation_mode = grpc ValidateToken
auth_grpc_public_keys_smoke = pass
```

## Rollback

Cloud Run rollback comes first:

```bash
gcloud run revisions list \
  --project on-the-block-2026 \
  --region asia-northeast3 \
  --service recommendation-service

gcloud run services update-traffic recommendation-service \
  --project on-the-block-2026 \
  --region asia-northeast3 \
  --to-revisions <previous-revision>=100
```

Rollback rules:

- Do not delete recommendation logs.
- Do not touch auth, survey, chat, map, gateway, or shared databases.
- Qdrant may be recreated from recommendation PostgreSQL.
- Staging PostgreSQL may be rebuilt only if no production user data is present.
