#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "image cache provision guard failed: $*" >&2
  exit 2
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 is required"
}

project_from_gcloud() {
  gcloud config get-value project 2>/dev/null || true
}

bucket_exists() {
  gcloud storage buckets describe "gs://${BUCKET}" \
    --project "$PROJECT" >/dev/null 2>&1
}

secret_exists() {
  local secret="$1"
  gcloud secrets describe "$secret" \
    --project "$PROJECT" >/dev/null 2>&1
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
      --labels service=recommendation,env=staging,purpose=beverage-image-cache \
      --data-file "$tmpfile"
  fi

  rm -f "$tmpfile"
}

require_command gcloud

PROJECT="${GCP_PROJECT:-$(project_from_gcloud)}"
LOCATION="${GCP_STORAGE_LOCATION:-asia-northeast3}"
BUCKET="${RECOMMENDATION_IMAGE_CACHE_BUCKET:-ontheblock-beverage-images-staging-${PROJECT}}"
CDN_BASE_URL="${RECOMMENDATION_IMAGE_CDN_BASE_URL:-https://storage.googleapis.com/${BUCKET}}"
CDN_BASE_URL_SECRET="${RECOMMENDATION_BEVERAGE_IMAGE_CDN_BASE_URL_SECRET:-recommendation-beverage-image-cdn-base-url-staging}"
RUNTIME_SERVICE_ACCOUNT="${RECOMMENDATION_RUNTIME_SERVICE_ACCOUNT:-recommendation-service-staging@${PROJECT}.iam.gserviceaccount.com}"
PUBLIC_READ="${RECOMMENDATION_IMAGE_CACHE_PUBLIC_READ:-0}"
APPLY="${RECOMMENDATION_IMAGE_CACHE_PROVISION_APPLY:-0}"
ADD_SECRET_VERSION="${RECOMMENDATION_IMAGE_CACHE_SECRET_ADD_VERSION:-0}"

[[ -n "$PROJECT" ]] || fail "GCP_PROJECT is required or gcloud project must be set"
[[ "$BUCKET" == *recommendation* || "$BUCKET" == *beverage* ]] \
  || fail "image cache bucket must clearly belong to recommendation beverage images"
[[ "$CDN_BASE_URL_SECRET" == *recommendation* \
  || "$CDN_BASE_URL_SECRET" == *rec* ]] \
  || fail "image CDN base URL secret must clearly belong to recommendation-service"
[[ "$CDN_BASE_URL" == https://* ]] \
  || fail "RECOMMENDATION_IMAGE_CDN_BASE_URL must be an https URL"

echo "recommendation beverage image cache target"
echo "project=${PROJECT}"
echo "location=${LOCATION}"
echo "bucket=${BUCKET}"
echo "cdn_base_url=${CDN_BASE_URL}"
echo "cdn_base_url_secret=${CDN_BASE_URL_SECRET}"
echo "runtime_service_account=${RUNTIME_SERVICE_ACCOUNT}"
echo "public_read=${PUBLIC_READ}"
echo "apply=${APPLY}"
echo "storage_policy=operator_managed_display_image_cache"

if bucket_exists; then
  echo "bucket_status=exists"
else
  echo "bucket_status=missing"
fi

if secret_exists "$CDN_BASE_URL_SECRET"; then
  echo "cdn_base_url_secret_status=exists"
else
  echo "cdn_base_url_secret_status=missing"
fi

if [[ "$PUBLIC_READ" != "1" && "$CDN_BASE_URL" == "https://storage.googleapis.com/${BUCKET}" ]]; then
  echo "warning=storage_googleapis_base_url_requires_public_read_or_signed_access"
fi

if [[ "$APPLY" != "1" ]]; then
  echo "dry_run=1 set RECOMMENDATION_IMAGE_CACHE_PROVISION_APPLY=1 to create missing resources"
  exit 0
fi

if ! bucket_exists; then
  gcloud storage buckets create "gs://${BUCKET}" \
    --project "$PROJECT" \
    --location "$LOCATION" \
    --uniform-bucket-level-access
fi

if [[ "$PUBLIC_READ" == "1" ]]; then
  gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
    --project "$PROJECT" \
    --member allUsers \
    --role roles/storage.objectViewer >/dev/null
else
  echo "public_read_binding=skipped set RECOMMENDATION_IMAGE_CACHE_PUBLIC_READ=1 for public MVP image URLs"
fi

write_secret_value "$CDN_BASE_URL_SECRET" "$CDN_BASE_URL"

gcloud secrets add-iam-policy-binding "$CDN_BASE_URL_SECRET" \
  --project "$PROJECT" \
  --member "serviceAccount:${RUNTIME_SERVICE_ACCOUNT}" \
  --role roles/secretmanager.secretAccessor >/dev/null

echo "recommendation beverage image cache provisioning complete"
echo "bucket=gs://${BUCKET}"
echo "cdn_base_url_secret=${CDN_BASE_URL_SECRET}"
echo "cdn_base_url=${CDN_BASE_URL}"
