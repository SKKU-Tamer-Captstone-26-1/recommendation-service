# Deployment Scripts

Scripts in this directory operate only on `recommendation-service` resources.
They must not point at auth, survey, chat, map, or gateway databases.

## Cloud Run gRPC Deployment

Use:

```bash
GCP_PROJECT=on-the-block-2026 \
GCP_REGION=asia-northeast3 \
RECOMMENDATION_DATABASE_SECRET=recommendation-db-dsn-staging \
RECOMMENDATION_QDRANT_URL_SECRET=recommendation-qdrant-url-staging \
RECOMMENDATION_QDRANT_API_KEY_SECRET=recommendation-qdrant-api-key-staging \
RECOMMENDATION_CLOUD_SQL_INSTANCE=on-the-block-2026:asia-northeast3:recommendation-postgres-staging \
bash scripts/deploy/gcp-cloud-run-grpc.sh
```

The script deploys the gRPC entrypoint:

```text
python -m app.grpc.main
```

Cloud Run is configured with:

```text
GRPC_HOST=0.0.0.0
GRPC_PORT=8080
--use-http2
```

By default, the service is deployed with `--no-allow-unauthenticated`.
Set `RECOMMENDATION_ALLOW_UNAUTHENTICATED=1` only for a reviewed staging smoke
path when the recommendation gRPC API still enforces auth metadata.

## Guards

The script refuses to deploy unless:

- `RECOMMENDATION_DATABASE_SECRET` is set.
- The database secret exists in Secret Manager.
- The database secret name clearly belongs to `recommendation-service`.
- Qdrant URL is provided by `RECOMMENDATION_QDRANT_URL_SECRET` or
  `RECOMMENDATION_QDRANT_URL`.

Known shared-service names such as auth, chat, survey, map, gateway, and
`DB_PASSWORD` are rejected as database secrets.

## Preflight Only

To validate project, Secret Manager, database-secret ownership, and Qdrant
configuration without deploying:

```bash
RECOMMENDATION_DEPLOY_CHECK_ONLY=1 \
GCP_PROJECT=on-the-block-2026 \
RECOMMENDATION_DATABASE_SECRET=recommendation-db-dsn-staging \
RECOMMENDATION_QDRANT_URL_SECRET=recommendation-qdrant-url-staging \
bash scripts/deploy/gcp-cloud-run-grpc.sh
```

This must pass before running the deploy without
`RECOMMENDATION_DEPLOY_CHECK_ONLY`.

## Staging Cloud SQL Provisioning

Dry-run inspection:

```bash
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-provision-staging-sql.sh
```

Create missing staging resources:

```bash
RECOMMENDATION_PROVISION_APPLY=1 \
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-provision-staging-sql.sh
```

Defaults:

```text
instance = recommendation-postgres-staging
database = recommendation_service
user = recommendation_user
secret = recommendation-db-dsn-staging
region = asia-northeast3
database_version = POSTGRES_16
edition = ENTERPRISE
tier = db-f1-micro
storage = 10 GB
```

The staging user receives `cloudsqlsuperuser` by default because the current
Alembic foundation migration creates `pgcrypto`, `postgis`, and `pg_trgm`.
Before production, split migration and runtime users so the Cloud Run serving
user does not need extension-creation privileges.

## Staging Qdrant Provisioning

Dry-run inspection:

```bash
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-provision-staging-qdrant.sh
```

Create or update the staging Qdrant Cloud Run service:

```bash
RECOMMENDATION_QDRANT_PROVISION_APPLY=1 \
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-provision-staging-qdrant.sh
```

Defaults:

```text
service = recommendation-qdrant-staging
image = docker.io/qdrant/qdrant:v1.18.0
api_key_secret = recommendation-qdrant-api-key-staging
url_secret = recommendation-qdrant-url-staging
service_account = recommendation-qdrant-staging
```

This is a staging-only, ephemeral Qdrant service. Qdrant remains rebuildable
from recommendation PostgreSQL and must not be treated as canonical storage.

## Staging Runtime IAM

Dry-run inspection:

```bash
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-provision-staging-runtime-iam.sh
```

Create the recommendation Cloud Run runtime service account and grant only the
needed staging access:

```bash
RECOMMENDATION_RUNTIME_IAM_APPLY=1 \
GCP_PROJECT=on-the-block-2026 \
bash scripts/deploy/gcp-provision-staging-runtime-iam.sh
```

Defaults:

```text
service_account = recommendation-service-staging
roles = roles/cloudsql.client
secret_access = recommendation-db-dsn-staging,
  recommendation-qdrant-url-staging,
  recommendation-qdrant-api-key-staging
```

## Staging Release Jobs

Run one release-prep job at a time:

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

Jobs run with the `recommendation-service-staging` service account, the Cloud
SQL connector, and recommendation-owned DB/Qdrant secrets.

When a safe deployed survey user or survey response is available, generate the
derived staging profile through the deployed survey-service adapter:

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

Set `RECOMMENDATION_SURVEY_ADAPTER_DRY_RUN=1` to validate mapping without
writing a profile. If survey-service requires a bearer credential, store it in
a recommendation-owned secret and set:

```text
SURVEY_SERVICE_GRPC_AUTH_BEARER_TOKEN_SECRET=recommendation-survey-grpc-token-staging
```

The adapter uses `survey_mapper_v1_1` and normalizes deployed category-key
answers, including `cognac -> brandy_cognac` and `*_k` budget labels.

Before writing a profile, validate the deployed result contract without DB
writes:

```bash
SURVEY_SMOKE_GRPC_ADDR=survey-service-vcuepibcwq-du.a.run.app:443 \
SURVEY_SMOKE_EXTERNAL_USER_ID=<safe-user-id> \
SMOKE_GRPC_TLS=1 \
python3 -m app.tools.deployed_smoke --mode survey
```

Use `SURVEY_SMOKE_RESPONSE_ID=<safe-survey-id>` instead of
`SURVEY_SMOKE_EXTERNAL_USER_ID` when validating by survey response ID.

## Verification

After deployment, run:

```bash
RECOMMENDATION_SMOKE_GRPC_ADDR=<cloud-run-host>:443 \
SMOKE_AUTH_BEARER_TOKEN=<safe-staging-token> \
SMOKE_GRPC_TLS=1 \
python3 -m app.tools.deployed_smoke --mode recommendation
```

For an active-profile smoke, also set:

```text
RECOMMENDATION_SMOKE_EXPECT_ACTIVE_PROFILE=true
RECOMMENDATION_SMOKE_RUN_BEVERAGE=true
RECOMMENDATION_SMOKE_RECORD_EVENT=true
```
