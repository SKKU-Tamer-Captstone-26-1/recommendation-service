#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "runtime IAM provision guard failed: $*" >&2
  exit 2
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 is required"
}

project_from_gcloud() {
  gcloud config get-value project 2>/dev/null || true
}

service_account_exists() {
  gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" \
    --project "$PROJECT" >/dev/null 2>&1
}

secret_exists() {
  local secret="$1"
  gcloud secrets describe "$secret" \
    --project "$PROJECT" >/dev/null 2>&1
}

grant_secret_accessor() {
  local secret="$1"
  gcloud secrets add-iam-policy-binding "$secret" \
    --project "$PROJECT" \
    --member "serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role roles/secretmanager.secretAccessor >/dev/null
}

require_command gcloud

PROJECT="${GCP_PROJECT:-$(project_from_gcloud)}"
SERVICE_ACCOUNT_ID="${RECOMMENDATION_RUNTIME_SERVICE_ACCOUNT_ID:-recommendation-service-staging}"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_ID}@${PROJECT}.iam.gserviceaccount.com"
DATABASE_SECRET="${RECOMMENDATION_DATABASE_SECRET:-recommendation-db-dsn-staging}"
QDRANT_URL_SECRET="${RECOMMENDATION_QDRANT_URL_SECRET:-recommendation-qdrant-url-staging}"
QDRANT_API_KEY_SECRET="${RECOMMENDATION_QDRANT_API_KEY_SECRET:-recommendation-qdrant-api-key-staging}"
APPLY="${RECOMMENDATION_RUNTIME_IAM_APPLY:-0}"

[[ -n "$PROJECT" ]] || fail "GCP_PROJECT is required or gcloud project must be set"
[[ "$SERVICE_ACCOUNT_ID" == *recommendation* || "$SERVICE_ACCOUNT_ID" == *rec* ]] \
  || fail "runtime service account must clearly belong to recommendation-service"

echo "recommendation runtime IAM target"
echo "project=${PROJECT}"
echo "service_account=${SERVICE_ACCOUNT_EMAIL}"
echo "database_secret=${DATABASE_SECRET}"
echo "qdrant_url_secret=${QDRANT_URL_SECRET}"
echo "qdrant_api_key_secret=${QDRANT_API_KEY_SECRET}"
echo "apply=${APPLY}"

if service_account_exists; then
  echo "service_account_status=exists"
else
  echo "service_account_status=missing"
fi

for secret in "$DATABASE_SECRET" "$QDRANT_URL_SECRET" "$QDRANT_API_KEY_SECRET"; do
  if secret_exists "$secret"; then
    echo "secret_status=exists secret=${secret}"
  else
    echo "secret_status=missing secret=${secret}"
  fi
done

if [[ "$APPLY" != "1" ]]; then
  echo "dry_run=1 set RECOMMENDATION_RUNTIME_IAM_APPLY=1 to create missing IAM"
  exit 0
fi

if ! service_account_exists; then
  gcloud iam service-accounts create "$SERVICE_ACCOUNT_ID" \
    --project "$PROJECT" \
    --display-name "Recommendation staging runtime"
fi

gcloud projects add-iam-policy-binding "$PROJECT" \
  --member "serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role roles/cloudsql.client >/dev/null

for secret in "$DATABASE_SECRET" "$QDRANT_URL_SECRET" "$QDRANT_API_KEY_SECRET"; do
  secret_exists "$secret" || fail "required secret does not exist: ${secret}"
  grant_secret_accessor "$secret"
done

echo "recommendation runtime IAM provisioning complete"
echo "service_account=${SERVICE_ACCOUNT_EMAIL}"
