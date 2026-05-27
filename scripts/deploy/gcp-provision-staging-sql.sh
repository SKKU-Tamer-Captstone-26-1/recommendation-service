#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "sql provision guard failed: $*" >&2
  exit 2
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 is required"
}

project_from_gcloud() {
  gcloud config get-value project 2>/dev/null || true
}

instance_exists() {
  gcloud sql instances describe "$SQL_INSTANCE" \
    --project "$PROJECT" >/dev/null 2>&1
}

database_exists() {
  gcloud sql databases describe "$SQL_DATABASE" \
    --instance "$SQL_INSTANCE" \
    --project "$PROJECT" >/dev/null 2>&1
}

user_exists() {
  [[ -n "$(gcloud sql users list \
    --instance "$SQL_INSTANCE" \
    --project "$PROJECT" \
    --filter "name=${SQL_USER}" \
    --format "value(name)" 2>/dev/null)" ]]
}

secret_exists() {
  gcloud secrets describe "$DATABASE_SECRET" \
    --project "$PROJECT" >/dev/null 2>&1
}

write_secret_data_file() {
  local path="$1"
  local password="$2"
  local database_url
  database_url="postgresql+psycopg://${SQL_USER}:${password}@/${SQL_DATABASE}?host=/cloudsql/${CONNECTION_NAME}"
  printf "%s" "$database_url" > "$path"
}

require_command gcloud
require_command openssl

PROJECT="${GCP_PROJECT:-$(project_from_gcloud)}"
REGION="${GCP_REGION:-asia-northeast3}"
SQL_INSTANCE="${RECOMMENDATION_SQL_INSTANCE:-recommendation-postgres-staging}"
SQL_DATABASE="${RECOMMENDATION_SQL_DATABASE:-recommendation_service}"
SQL_USER="${RECOMMENDATION_SQL_USER:-recommendation_user}"
DATABASE_SECRET="${RECOMMENDATION_DATABASE_SECRET:-recommendation-db-dsn-staging}"
DATABASE_VERSION="${RECOMMENDATION_SQL_DATABASE_VERSION:-POSTGRES_16}"
SQL_EDITION="${RECOMMENDATION_SQL_EDITION:-ENTERPRISE}"
SQL_TIER="${RECOMMENDATION_SQL_TIER:-db-f1-micro}"
STORAGE_SIZE_GB="${RECOMMENDATION_SQL_STORAGE_SIZE_GB:-10}"
BACKUP_START_TIME="${RECOMMENDATION_SQL_BACKUP_START_TIME:-18:00}"
USER_ROLES="${RECOMMENDATION_SQL_USER_ROLES:-cloudsqlsuperuser}"
APPLY="${RECOMMENDATION_PROVISION_APPLY:-0}"
ADD_SECRET_VERSION="${RECOMMENDATION_DATABASE_SECRET_ADD_VERSION:-0}"
CONNECTION_NAME="${PROJECT}:${REGION}:${SQL_INSTANCE}"

[[ -n "$PROJECT" ]] || fail "GCP_PROJECT is required or gcloud project must be set"
[[ "$SQL_INSTANCE" == *recommendation* || "$SQL_INSTANCE" == *rec* ]] \
  || fail "SQL instance name must clearly belong to recommendation-service"
[[ "$DATABASE_SECRET" == *recommendation* || "$DATABASE_SECRET" == *rec* ]] \
  || fail "database secret name must clearly belong to recommendation-service"

echo "recommendation SQL provisioning target"
echo "project=${PROJECT}"
echo "region=${REGION}"
echo "instance=${SQL_INSTANCE}"
echo "database=${SQL_DATABASE}"
echo "user=${SQL_USER}"
echo "database_secret=${DATABASE_SECRET}"
echo "connection_name=${CONNECTION_NAME}"
echo "edition=${SQL_EDITION}"
echo "apply=${APPLY}"

if instance_exists; then
  echo "instance_status=exists"
else
  echo "instance_status=missing"
fi

if instance_exists && database_exists; then
  echo "database_status=exists"
else
  echo "database_status=missing"
fi

if instance_exists && user_exists; then
  echo "user_status=exists"
else
  echo "user_status=missing"
fi

if secret_exists; then
  echo "secret_status=exists"
else
  echo "secret_status=missing"
fi

if [[ "$APPLY" != "1" ]]; then
  echo "dry_run=1 set RECOMMENDATION_PROVISION_APPLY=1 to create missing resources"
  exit 0
fi

if ! instance_exists; then
  gcloud sql instances create "$SQL_INSTANCE" \
    --project "$PROJECT" \
    --region "$REGION" \
    --database-version "$DATABASE_VERSION" \
    --edition "$SQL_EDITION" \
    --tier "$SQL_TIER" \
    --storage-size "$STORAGE_SIZE_GB" \
    --availability-type ZONAL \
    --backup-start-time "$BACKUP_START_TIME" \
    --storage-auto-increase \
    --no-deletion-protection
fi

if ! database_exists; then
  gcloud sql databases create "$SQL_DATABASE" \
    --project "$PROJECT" \
    --instance "$SQL_INSTANCE"
fi

PASSWORD="${RECOMMENDATION_SQL_USER_PASSWORD:-}"
created_user=0
if ! user_exists; then
  PASSWORD="${PASSWORD:-$(openssl rand -hex 24)}"
  user_args=(
    "$SQL_USER"
    --project "$PROJECT"
    --instance "$SQL_INSTANCE"
    --password "$PASSWORD"
  )
  if [[ -n "$USER_ROLES" ]]; then
    user_args+=(--database-roles "$USER_ROLES")
  fi
  gcloud sql users create "${user_args[@]}"
  created_user=1
fi

if secret_exists && [[ "$ADD_SECRET_VERSION" != "1" ]]; then
  echo "secret_write=skipped existing_secret=1"
elif [[ "$created_user" == "1" || -n "$PASSWORD" ]]; then
  tmpfile="$(mktemp)"
  chmod 600 "$tmpfile"
  trap 'rm -f "$tmpfile"' EXIT
  write_secret_data_file "$tmpfile" "$PASSWORD"
  if secret_exists; then
    gcloud secrets versions add "$DATABASE_SECRET" \
      --project "$PROJECT" \
      --data-file "$tmpfile"
  else
    gcloud secrets create "$DATABASE_SECRET" \
      --project "$PROJECT" \
      --replication-policy automatic \
      --labels service=recommendation,env=staging \
      --data-file "$tmpfile"
  fi
else
  fail "database user exists but no password was provided to create/update secret"
fi

echo "recommendation SQL provisioning complete"
echo "database_secret=${DATABASE_SECRET}"
echo "connection_name=${CONNECTION_NAME}"
