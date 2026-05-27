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
```
