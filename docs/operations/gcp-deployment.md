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
```

The `DATABASE_URL` secret must point only at the recommendation-owned database.
Do not reuse `DB_PASSWORD`, `chat-db-dsn-staging`, auth-service credentials, or
any service-owned database secret from another repo.

The Cloud Run runtime service account must have Secret Manager access only for
the recommendation-owned secrets it needs. Do not grant broad access to other
service secrets.

## Deploy gRPC Service

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
JWT_ISSUER=on-the-block-auth
JWT_AUDIENCE=recommendation-service
SURVEY_SERVICE_URL=https://survey-service-vcuepibcwq-du.a.run.app
SURVEY_SERVICE_GRPC_ADDR=survey-service-vcuepibcwq-du.a.run.app:443
SYNC_WORKER_ENABLED=false
```

`SYNC_WORKER_ENABLED=false` is intentional for this deployment slice because
the deployed survey-service does not yet expose the cursor-based production sync
contract. Use the controlled survey result adapter for safe staging profile
generation until that contract exists.

By default, the script deploys with:

```text
--no-allow-unauthenticated
```

Set:

```bash
RECOMMENDATION_ALLOW_UNAUTHENTICATED=1
```

only for a reviewed staging path where Cloud Run ingress is public but the
recommendation gRPC service still verifies bearer auth metadata.

## Migrate, Seed, and Rebuild

After the dedicated database exists and before serving Flutter traffic:

```bash
DATABASE_URL=<recommendation-owned-dsn> python3 -m alembic upgrade head
DATABASE_URL=<recommendation-owned-dsn> python3 -m app.tools.beverage_import --stage --promote-seed
DATABASE_URL=<recommendation-owned-dsn> python3 -m app.tools.beverage_catalog_audit --database
DATABASE_URL=<recommendation-owned-dsn> python3 -m app.tools.qdrant_rebuild --owner-type beverage_item --recreate
```

The actual secret value must be read from Secret Manager or injected by the
deployment environment. Do not paste real DSNs into committed files.

## Survey Adapter Smoke

When a safe deployed survey user or survey ID is available:

```bash
SURVEY_SERVICE_GRPC_ADDR=survey-service-vcuepibcwq-du.a.run.app:443 \
SURVEY_SERVICE_GRPC_AUTH_BEARER_TOKEN=<token-if-required> \
DATABASE_URL=<recommendation-owned-dsn> \
python3 -m app.tools.survey_result_adapter \
  --external-user-id <safe-user-id>
```

This creates a derived recommendation profile from the deployed survey result.
It is staging-only and does not replace cursor-based production sync.

## Deployed Smoke

After Cloud Run reports a ready revision:

```bash
RECOMMENDATION_SMOKE_GRPC_ADDR=<recommendation-cloud-run-host>:443 \
SMOKE_AUTH_BEARER_TOKEN=<safe-staging-token> \
SMOKE_GRPC_TLS=1 \
python3 -m app.tools.deployed_smoke --mode recommendation
```

For a stronger active-profile smoke:

```bash
RECOMMENDATION_SMOKE_GRPC_ADDR=<recommendation-cloud-run-host>:443 \
SMOKE_AUTH_BEARER_TOKEN=<safe-staging-token> \
RECOMMENDATION_SMOKE_EXPECT_ACTIVE_PROFILE=true \
RECOMMENDATION_SMOKE_RUN_BEVERAGE=true \
SMOKE_GRPC_TLS=1 \
python3 -m app.tools.deployed_smoke --mode recommendation
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
