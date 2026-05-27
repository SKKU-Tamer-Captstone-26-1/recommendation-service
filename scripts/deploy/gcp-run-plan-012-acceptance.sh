#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "plan 012 acceptance failed: $*" >&2
  exit 2
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 is required"
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

require_command python3

safe_user_id="${PLAN012_SAFE_SURVEY_EXTERNAL_USER_ID:-${SURVEY_SMOKE_EXTERNAL_USER_ID:-${RECOMMENDATION_SURVEY_ADAPTER_EXTERNAL_USER_ID:-}}}"
safe_survey_id="${PLAN012_SAFE_SURVEY_RESPONSE_ID:-${SURVEY_SMOKE_RESPONSE_ID:-${RECOMMENDATION_SURVEY_ADAPTER_RESPONSE_ID:-}}}"
expected_user_id="${PLAN012_EXPECTED_EXTERNAL_USER_ID:-${AUTH_SMOKE_EXPECTED_USER_ID:-}}"

[[ -n "$safe_user_id" || -n "$safe_survey_id" ]] \
  || fail "set PLAN012_SAFE_SURVEY_EXTERNAL_USER_ID or PLAN012_SAFE_SURVEY_RESPONSE_ID"
[[ -z "$safe_user_id" || -z "$safe_survey_id" ]] \
  || fail "set only one of PLAN012_SAFE_SURVEY_EXTERNAL_USER_ID or PLAN012_SAFE_SURVEY_RESPONSE_ID"
[[ -n "${SMOKE_AUTH_BEARER_TOKEN:-}" ]] \
  || fail "SMOKE_AUTH_BEARER_TOKEN is required"

if [[ -n "$safe_user_id" ]]; then
  expected_user_id="${expected_user_id:-$safe_user_id}"
elif [[ -z "$expected_user_id" ]]; then
  fail "PLAN012_EXPECTED_EXTERNAL_USER_ID is required when using PLAN012_SAFE_SURVEY_RESPONSE_ID"
fi

[[ "${PLAN012_PROFILE_ALREADY_ACTIVE:-0}" == "1" \
  || "${PLAN012_ALLOW_PROFILE_WRITE:-0}" == "1" ]] \
  || fail "set PLAN012_ALLOW_PROFILE_WRITE=1 or PLAN012_PROFILE_ALREADY_ACTIVE=1"
[[ "${PLAN012_ALLOW_EVENT_WRITE:-0}" == "1" ]] \
  || fail "set PLAN012_ALLOW_EVENT_WRITE=1 to record the smoke impression event"

export SMOKE_GRPC_TLS="${SMOKE_GRPC_TLS:-1}"
export AUTH_SMOKE_GRPC_ADDR="${AUTH_SMOKE_GRPC_ADDR:-authorization-service-44649239380.asia-northeast3.run.app:443}"
export AUTH_SMOKE_EXPECTED_ISSUER="${AUTH_SMOKE_EXPECTED_ISSUER:-on-the-block-auth}"
export AUTH_SMOKE_EXPECTED_AUDIENCE="${AUTH_SMOKE_EXPECTED_AUDIENCE:-recommendation-service}"
export AUTH_SMOKE_EXPECTED_USER_ID="$expected_user_id"
export SURVEY_SMOKE_GRPC_ADDR="${SURVEY_SMOKE_GRPC_ADDR:-survey-service-vcuepibcwq-du.a.run.app:443}"
export SURVEY_SMOKE_EXPECTED_USER_ID="$expected_user_id"
export RECOMMENDATION_SMOKE_GRPC_ADDR="${RECOMMENDATION_SMOKE_GRPC_ADDR:-recommendation-service-vcuepibcwq-du.a.run.app:443}"

if [[ -n "$safe_user_id" ]]; then
  export SURVEY_SMOKE_EXTERNAL_USER_ID="$safe_user_id"
  unset SURVEY_SMOKE_RESPONSE_ID || true
else
  export SURVEY_SMOKE_RESPONSE_ID="$safe_survey_id"
  unset SURVEY_SMOKE_EXTERNAL_USER_ID || true
fi

echo "plan012 acceptance: auth token validation"
python3 -m app.tools.deployed_smoke --mode auth

echo "plan012 acceptance: deployed survey result contract"
python3 -m app.tools.deployed_smoke --mode survey

if [[ "${PLAN012_PROFILE_ALREADY_ACTIVE:-0}" != "1" ]]; then
  require_command gcloud
  export GCP_PROJECT="${GCP_PROJECT:-on-the-block-2026}"
  if [[ -n "$safe_user_id" ]]; then
    echo "plan012 acceptance: generate profile from survey user"
    RECOMMENDATION_JOB_MODE=survey-adapter-user \
    RECOMMENDATION_SURVEY_ADAPTER_EXTERNAL_USER_ID="$safe_user_id" \
    bash scripts/deploy/gcp-run-staging-job.sh
  else
    echo "plan012 acceptance: generate profile from survey response"
    RECOMMENDATION_JOB_MODE=survey-adapter-response \
    RECOMMENDATION_SURVEY_ADAPTER_RESPONSE_ID="$safe_survey_id" \
    bash scripts/deploy/gcp-run-staging-job.sh
  fi
else
  echo "plan012 acceptance: profile generation skipped, marked already active"
fi

export RECOMMENDATION_SMOKE_EXPECT_ACTIVE_PROFILE=true
export RECOMMENDATION_SMOKE_RUN_BEVERAGE=true
export RECOMMENDATION_SMOKE_RECORD_EVENT=true

echo "plan012 acceptance: recommendation profile, beverage, and event smoke"
python3 -m app.tools.deployed_smoke --mode recommendation

echo "plan012 acceptance passed"
