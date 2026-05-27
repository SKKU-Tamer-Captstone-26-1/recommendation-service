#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "staging job guard failed: $*" >&2
  exit 2
}

join_by_comma() {
  local IFS=,
  echo "$*"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 is required"
}

project_from_gcloud() {
  gcloud config get-value project 2>/dev/null || true
}

require_secret() {
  local project="$1"
  local secret="$2"
  gcloud secrets describe "$secret" --project "$project" >/dev/null 2>&1 \
    || fail "Secret Manager secret does not exist in project ${project}: ${secret}"
}

resolve_job() {
  local mode="$1"
  case "$mode" in
    migrate)
      JOB_NAME="${RECOMMENDATION_JOB_NAME:-recommendation-migrate-staging}"
      JOB_ARGS=(-m alembic upgrade head)
      ;;
    seed)
      JOB_NAME="${RECOMMENDATION_JOB_NAME:-recommendation-seed-staging}"
      JOB_ARGS=(-m app.tools.beverage_import --stage --promote-seed)
      ;;
    catalog-audit)
      JOB_NAME="${RECOMMENDATION_JOB_NAME:-recommendation-catalog-audit-staging}"
      JOB_ARGS=(-m app.tools.beverage_catalog_audit --database)
      ;;
    qdrant-rebuild)
      JOB_NAME="${RECOMMENDATION_JOB_NAME:-recommendation-qdrant-rebuild-staging}"
      JOB_ARGS=(-m app.tools.qdrant_rebuild --owner-type beverage_item --recreate)
      ;;
    qdrant-smoke)
      JOB_NAME="${RECOMMENDATION_JOB_NAME:-recommendation-qdrant-smoke-staging}"
      JOB_ARGS=(-m app.tools.qdrant_index_smoke --owner-type beverage_item)
      ;;
    beverage-smoke)
      JOB_NAME="${RECOMMENDATION_JOB_NAME:-recommendation-beverage-smoke-staging}"
      JOB_ARGS=(-m app.tools.beverage_recommendation_smoke)
      ;;
    *)
      fail "unsupported RECOMMENDATION_JOB_MODE: ${mode}"
      ;;
  esac
}

require_command gcloud

PROJECT="${GCP_PROJECT:-$(project_from_gcloud)}"
REGION="${GCP_REGION:-asia-northeast3}"
MODE="${RECOMMENDATION_JOB_MODE:-}"
SOURCE_DIR="${RECOMMENDATION_DEPLOY_SOURCE:-.}"
IMAGE="${RECOMMENDATION_IMAGE:-}"
DATABASE_SECRET="${RECOMMENDATION_DATABASE_SECRET:-recommendation-db-dsn-staging}"
QDRANT_URL_SECRET="${RECOMMENDATION_QDRANT_URL_SECRET:-recommendation-qdrant-url-staging}"
QDRANT_API_KEY_SECRET="${RECOMMENDATION_QDRANT_API_KEY_SECRET:-recommendation-qdrant-api-key-staging}"
CLOUD_SQL_INSTANCE="${RECOMMENDATION_CLOUD_SQL_INSTANCE:-${PROJECT}:asia-northeast3:recommendation-postgres-staging}"
SERVICE_ACCOUNT="${RECOMMENDATION_RUNTIME_SERVICE_ACCOUNT:-recommendation-service-staging@${PROJECT}.iam.gserviceaccount.com}"
TASK_TIMEOUT="${RECOMMENDATION_JOB_TASK_TIMEOUT:-1800s}"
MEMORY="${RECOMMENDATION_JOB_MEMORY:-1Gi}"
CPU="${RECOMMENDATION_JOB_CPU:-1}"

[[ -n "$PROJECT" ]] || fail "GCP_PROJECT is required or gcloud project must be set"
[[ -n "$MODE" ]] || fail "RECOMMENDATION_JOB_MODE is required"
[[ "$DATABASE_SECRET" == *recommendation* || "$DATABASE_SECRET" == *rec* ]] \
  || fail "database secret must clearly belong to recommendation-service"
[[ "$QDRANT_URL_SECRET" == *recommendation* || "$QDRANT_URL_SECRET" == *rec* ]] \
  || fail "Qdrant URL secret must clearly belong to recommendation-service"
[[ "$QDRANT_API_KEY_SECRET" == *recommendation* || "$QDRANT_API_KEY_SECRET" == *rec* ]] \
  || fail "Qdrant API key secret must clearly belong to recommendation-service"

resolve_job "$MODE"
require_secret "$PROJECT" "$DATABASE_SECRET"
require_secret "$PROJECT" "$QDRANT_URL_SECRET"
require_secret "$PROJECT" "$QDRANT_API_KEY_SECRET"

target_args=()
if [[ -n "$IMAGE" ]]; then
  target_args=(--image "$IMAGE")
else
  target_args=(--source "$SOURCE_DIR")
fi

env_vars=(
  "APP_ENV=staging"
  "QDRANT_INDEXING_ENABLED=true"
)
secret_envs=(
  "DATABASE_URL=${DATABASE_SECRET}:latest"
  "QDRANT_URL=${QDRANT_URL_SECRET}:latest"
  "QDRANT_API_KEY=${QDRANT_API_KEY_SECRET}:latest"
)

echo "deploying staging job mode=${MODE} job=${JOB_NAME}"
echo "project=${PROJECT} region=${REGION}"
echo "cloud_sql_instance=${CLOUD_SQL_INSTANCE}"
echo "service_account=${SERVICE_ACCOUNT}"

gcloud run jobs deploy "$JOB_NAME" \
  --project "$PROJECT" \
  --region "$REGION" \
  "${target_args[@]}" \
  --command=python \
  --args="$(join_by_comma "${JOB_ARGS[@]}")" \
  --service-account "$SERVICE_ACCOUNT" \
  --set-cloudsql-instances "$CLOUD_SQL_INSTANCE" \
  --set-env-vars "$(join_by_comma "${env_vars[@]}")" \
  --set-secrets "$(join_by_comma "${secret_envs[@]}")" \
  --max-retries 0 \
  --tasks 1 \
  --parallelism 1 \
  --task-timeout "$TASK_TIMEOUT" \
  --memory "$MEMORY" \
  --cpu "$CPU" \
  --execute-now \
  --wait \
  --quiet
