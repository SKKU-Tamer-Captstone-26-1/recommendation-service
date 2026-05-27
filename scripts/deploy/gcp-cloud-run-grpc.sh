#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "deploy guard failed: $*" >&2
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

assert_recommendation_database_secret() {
  local secret="$1"
  local lower
  lower="$(printf "%s" "$secret" | tr "[:upper:]" "[:lower:]")"

  case "$lower" in
    db_password|*auth*|*chat*|*survey*|*map*|*gateway*)
      fail "database secret appears to belong to another service: ${secret}"
      ;;
  esac

  if [[ "$lower" != *recommendation* && "$lower" != *rec* ]]; then
    fail "database secret name must clearly belong to recommendation-service: ${secret}"
  fi
}

require_command gcloud

PROJECT="${GCP_PROJECT:-$(project_from_gcloud)}"
REGION="${GCP_REGION:-asia-northeast3}"
SERVICE="${RECOMMENDATION_CLOUD_RUN_SERVICE:-recommendation-service}"
SOURCE_DIR="${RECOMMENDATION_DEPLOY_SOURCE:-.}"
IMAGE="${RECOMMENDATION_IMAGE:-}"
DATABASE_SECRET="${RECOMMENDATION_DATABASE_SECRET:-}"
QDRANT_URL_SECRET="${RECOMMENDATION_QDRANT_URL_SECRET:-}"
QDRANT_API_KEY_SECRET="${RECOMMENDATION_QDRANT_API_KEY_SECRET:-}"
QDRANT_URL_VALUE="${RECOMMENDATION_QDRANT_URL:-}"
CLOUD_SQL_INSTANCE="${RECOMMENDATION_CLOUD_SQL_INSTANCE:-}"
SERVICE_ACCOUNT="${RECOMMENDATION_RUNTIME_SERVICE_ACCOUNT:-recommendation-service-staging@${PROJECT}.iam.gserviceaccount.com}"
ALLOW_UNAUTHENTICATED="${RECOMMENDATION_ALLOW_UNAUTHENTICATED:-0}"
CHECK_ONLY="${RECOMMENDATION_DEPLOY_CHECK_ONLY:-0}"

AUTH_SERVICE_URL="${AUTH_SERVICE_URL:-https://authorization-service-vcuepibcwq-du.a.run.app}"
AUTH_JWKS_URL="${AUTH_JWKS_URL:-https://authorization-service-vcuepibcwq-du.a.run.app/.well-known/jwks.json}"
AUTH_SERVICE_GRPC_ADDR="${AUTH_SERVICE_GRPC_ADDR:-authorization-service-vcuepibcwq-du.a.run.app:443}"
AUTH_TOKEN_VALIDATION_MODE="${AUTH_TOKEN_VALIDATION_MODE:-grpc}"
AUTH_SERVICE_GRPC_TLS="${AUTH_SERVICE_GRPC_TLS:-true}"
JWT_ISSUER="${JWT_ISSUER:-on-the-block-auth}"
JWT_AUDIENCE="${JWT_AUDIENCE:-recommendation-service}"
SURVEY_SERVICE_URL="${SURVEY_SERVICE_URL:-https://survey-service-vcuepibcwq-du.a.run.app}"
SURVEY_SERVICE_GRPC_ADDR="${SURVEY_SERVICE_GRPC_ADDR:-survey-service-vcuepibcwq-du.a.run.app:443}"

[[ -n "$PROJECT" ]] || fail "GCP_PROJECT is required or gcloud project must be set"
[[ -n "$DATABASE_SECRET" ]] || fail "RECOMMENDATION_DATABASE_SECRET is required"
[[ -n "$QDRANT_URL_SECRET" || -n "$QDRANT_URL_VALUE" ]] \
  || fail "set RECOMMENDATION_QDRANT_URL_SECRET or RECOMMENDATION_QDRANT_URL"

assert_recommendation_database_secret "$DATABASE_SECRET"
require_secret "$PROJECT" "$DATABASE_SECRET"

secret_envs=("DATABASE_URL=${DATABASE_SECRET}:latest")
if [[ -n "$QDRANT_URL_SECRET" ]]; then
  require_secret "$PROJECT" "$QDRANT_URL_SECRET"
  secret_envs+=("QDRANT_URL=${QDRANT_URL_SECRET}:latest")
fi
if [[ -n "$QDRANT_API_KEY_SECRET" ]]; then
  require_secret "$PROJECT" "$QDRANT_API_KEY_SECRET"
  secret_envs+=("QDRANT_API_KEY=${QDRANT_API_KEY_SECRET}:latest")
fi

env_vars=(
  "APP_ENV=staging"
  "GRPC_HOST=0.0.0.0"
  "GRPC_PORT=8080"
  "AUTH_SERVICE_URL=${AUTH_SERVICE_URL}"
  "AUTH_JWKS_URL=${AUTH_JWKS_URL}"
  "AUTH_SERVICE_GRPC_ADDR=${AUTH_SERVICE_GRPC_ADDR}"
  "AUTH_TOKEN_VALIDATION_MODE=${AUTH_TOKEN_VALIDATION_MODE}"
  "AUTH_SERVICE_GRPC_TLS=${AUTH_SERVICE_GRPC_TLS}"
  "JWT_ISSUER=${JWT_ISSUER}"
  "JWT_AUDIENCE=${JWT_AUDIENCE}"
  "SURVEY_SERVICE_URL=${SURVEY_SERVICE_URL}"
  "SURVEY_SERVICE_GRPC_ADDR=${SURVEY_SERVICE_GRPC_ADDR}"
  "SYNC_WORKER_ENABLED=false"
)
if [[ -n "$QDRANT_URL_VALUE" && -z "$QDRANT_URL_SECRET" ]]; then
  env_vars+=("QDRANT_URL=${QDRANT_URL_VALUE}")
fi

target_args=()
if [[ -n "$IMAGE" ]]; then
  target_args=(--image "$IMAGE")
else
  target_args=(--source "$SOURCE_DIR")
fi

auth_args=(--no-allow-unauthenticated)
if [[ "$ALLOW_UNAUTHENTICATED" == "1" ]]; then
  auth_args=(--allow-unauthenticated)
fi

optional_args=()
if [[ -n "$CLOUD_SQL_INSTANCE" ]]; then
  optional_args+=(--add-cloudsql-instances "$CLOUD_SQL_INSTANCE")
fi
if [[ -n "$SERVICE_ACCOUNT" ]]; then
  optional_args+=(--service-account "$SERVICE_ACCOUNT")
fi

echo "deploying ${SERVICE} to project=${PROJECT} region=${REGION}"
echo "database_secret=${DATABASE_SECRET} cloud_sql_instance=${CLOUD_SQL_INSTANCE:-none}"
echo "qdrant_url_source=$([[ -n "$QDRANT_URL_SECRET" ]] && echo secret || echo env)"
echo "allow_unauthenticated=${ALLOW_UNAUTHENTICATED}"

if [[ "$CHECK_ONLY" == "1" ]]; then
  echo "deploy preflight passed"
  exit 0
fi

gcloud run deploy "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --platform managed \
  "${target_args[@]}" \
  --command=python \
  --args=-m,app.grpc.main \
  --port=8080 \
  --use-http2 \
  --set-env-vars "$(join_by_comma "${env_vars[@]}")" \
  --set-secrets "$(join_by_comma "${secret_envs[@]}")" \
  "${auth_args[@]}" \
  "${optional_args[@]}"
