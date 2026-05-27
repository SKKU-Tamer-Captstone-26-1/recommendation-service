#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "qdrant provision guard failed: $*" >&2
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

service_exists() {
  gcloud run services describe "$SERVICE" \
    --project "$PROJECT" \
    --region "$REGION" >/dev/null 2>&1
}

service_url() {
  gcloud run services describe "$SERVICE" \
    --project "$PROJECT" \
    --region "$REGION" \
    --format "value(status.url)"
}

write_secret_value() {
  local secret="$1"
  local value="$2"
  local tmpfile
  tmpfile="$(mktemp)"
  chmod 600 "$tmpfile"
  printf "%s" "$value" > "$tmpfile"

  if secret_exists "$secret"; then
    if [[ "$ADD_SECRET_VERSION" == "1" ]]; then
      gcloud secrets versions add "$secret" \
        --project "$PROJECT" \
        --data-file "$tmpfile"
    else
      echo "secret_write=skipped secret=${secret} existing_secret=1"
    fi
  else
    gcloud secrets create "$secret" \
      --project "$PROJECT" \
      --replication-policy automatic \
      --labels service=recommendation,env=staging \
      --data-file "$tmpfile"
  fi

  rm -f "$tmpfile"
}

require_command gcloud
require_command openssl

PROJECT="${GCP_PROJECT:-$(project_from_gcloud)}"
REGION="${GCP_REGION:-asia-northeast3}"
SERVICE="${RECOMMENDATION_QDRANT_SERVICE:-recommendation-qdrant-staging}"
IMAGE="${RECOMMENDATION_QDRANT_IMAGE:-docker.io/qdrant/qdrant:v1.12.4}"
API_KEY_SECRET="${RECOMMENDATION_QDRANT_API_KEY_SECRET:-recommendation-qdrant-api-key-staging}"
URL_SECRET="${RECOMMENDATION_QDRANT_URL_SECRET:-recommendation-qdrant-url-staging}"
SERVICE_ACCOUNT_ID="${RECOMMENDATION_QDRANT_SERVICE_ACCOUNT_ID:-recommendation-qdrant-staging}"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_ID}@${PROJECT}.iam.gserviceaccount.com"
MEMORY="${RECOMMENDATION_QDRANT_MEMORY:-1Gi}"
CPU="${RECOMMENDATION_QDRANT_CPU:-1}"
MAX_INSTANCES="${RECOMMENDATION_QDRANT_MAX_INSTANCES:-1}"
MIN_INSTANCES="${RECOMMENDATION_QDRANT_MIN_INSTANCES:-0}"
APPLY="${RECOMMENDATION_QDRANT_PROVISION_APPLY:-0}"
ADD_SECRET_VERSION="${RECOMMENDATION_QDRANT_SECRET_ADD_VERSION:-0}"

[[ -n "$PROJECT" ]] || fail "GCP_PROJECT is required or gcloud project must be set"
[[ "$SERVICE" == *recommendation* || "$SERVICE" == *rec* ]] \
  || fail "Qdrant service name must clearly belong to recommendation-service"
[[ "$API_KEY_SECRET" == *recommendation* || "$API_KEY_SECRET" == *rec* ]] \
  || fail "Qdrant API key secret must clearly belong to recommendation-service"
[[ "$URL_SECRET" == *recommendation* || "$URL_SECRET" == *rec* ]] \
  || fail "Qdrant URL secret must clearly belong to recommendation-service"

echo "recommendation Qdrant provisioning target"
echo "project=${PROJECT}"
echo "region=${REGION}"
echo "service=${SERVICE}"
echo "image=${IMAGE}"
echo "api_key_secret=${API_KEY_SECRET}"
echo "url_secret=${URL_SECRET}"
echo "service_account=${SERVICE_ACCOUNT_EMAIL}"
echo "apply=${APPLY}"
echo "storage_policy=ephemeral_rebuild_from_postgresql"

if service_account_exists; then
  echo "service_account_status=exists"
else
  echo "service_account_status=missing"
fi

if secret_exists "$API_KEY_SECRET"; then
  echo "api_key_secret_status=exists"
else
  echo "api_key_secret_status=missing"
fi

if service_exists; then
  echo "service_status=exists"
  echo "service_url=$(service_url)"
else
  echo "service_status=missing"
fi

if secret_exists "$URL_SECRET"; then
  echo "url_secret_status=exists"
else
  echo "url_secret_status=missing"
fi

if [[ "$APPLY" != "1" ]]; then
  echo "dry_run=1 set RECOMMENDATION_QDRANT_PROVISION_APPLY=1 to create missing resources"
  exit 0
fi

if ! service_account_exists; then
  gcloud iam service-accounts create "$SERVICE_ACCOUNT_ID" \
    --project "$PROJECT" \
    --display-name "Recommendation staging Qdrant"
fi

if ! secret_exists "$API_KEY_SECRET"; then
  write_secret_value "$API_KEY_SECRET" "$(openssl rand -hex 32)"
fi

gcloud secrets add-iam-policy-binding "$API_KEY_SECRET" \
  --project "$PROJECT" \
  --member "serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role roles/secretmanager.secretAccessor >/dev/null

gcloud run deploy "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --platform managed \
  --image "$IMAGE" \
  --port 6333 \
  --memory "$MEMORY" \
  --cpu "$CPU" \
  --min-instances "$MIN_INSTANCES" \
  --max-instances "$MAX_INSTANCES" \
  --allow-unauthenticated \
  --service-account "$SERVICE_ACCOUNT_EMAIL" \
  --set-env-vars "QDRANT__LOG_LEVEL=INFO" \
  --set-secrets "QDRANT__SERVICE__API_KEY=${API_KEY_SECRET}:latest" \
  --quiet

QDRANT_URL="$(service_url)"
[[ -n "$QDRANT_URL" ]] || fail "Cloud Run did not report a Qdrant service URL"
write_secret_value "$URL_SECRET" "$QDRANT_URL"

echo "recommendation Qdrant provisioning complete"
echo "qdrant_url_secret=${URL_SECRET}"
echo "qdrant_api_key_secret=${API_KEY_SECRET}"
echo "qdrant_url=${QDRANT_URL}"
