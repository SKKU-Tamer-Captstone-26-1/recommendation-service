#!/usr/bin/env bash
set -euo pipefail

TARGET="${RECOMMENDATION_LOAD_GRPC_ADDR:-localhost:50051}"
PROTO="${RECOMMENDATION_LOAD_PROTO:-proto/recommendation/v1/recommendation.proto}"
IMPORT_PATH="${RECOMMENDATION_LOAD_PROTO_PATH:-proto}"
SERVICE="ontheblock.recommendation.v1.RecommendationService"
PROFILE="${RECOMMENDATION_LOAD_PROFILE:-smoke}"
TOKEN="${SMOKE_AUTH_BEARER_TOKEN:-}"
TLS="${RECOMMENDATION_LOAD_TLS:-0}"
METHOD="${1:-mixed}"

case "$PROFILE" in
  smoke)
    RPS="${RECOMMENDATION_LOAD_RPS:-5}"
    DURATION="${RECOMMENDATION_LOAD_DURATION:-5m}"
    ;;
  beta)
    RPS="${RECOMMENDATION_LOAD_RPS:-20}"
    DURATION="${RECOMMENDATION_LOAD_DURATION:-10m}"
    ;;
  peak)
    RPS="${RECOMMENDATION_LOAD_RPS:-50}"
    DURATION="${RECOMMENDATION_LOAD_DURATION:-10m}"
    ;;
  stress)
    RPS="${RECOMMENDATION_LOAD_RPS:-100}"
    DURATION="${RECOMMENDATION_LOAD_DURATION:-10m}"
    ;;
  soak)
    RPS="${RECOMMENDATION_LOAD_RPS:-50}"
    DURATION="${RECOMMENDATION_LOAD_DURATION:-2h}"
    ;;
  *)
    echo "unsupported RECOMMENDATION_LOAD_PROFILE: $PROFILE" >&2
    exit 2
    ;;
esac

if ! command -v ghz >/dev/null 2>&1; then
  echo "ghz is required: https://ghz.sh/" >&2
  exit 127
fi

AUTH_ARGS=()
if [[ -n "$TOKEN" ]]; then
  AUTH_ARGS+=(--metadata "authorization=Bearer $TOKEN")
fi

TLS_ARGS=()
if [[ "$TLS" == "1" || "$TARGET" == *":443" ]]; then
  if [[ -n "${RECOMMENDATION_LOAD_CA_CERT:-}" ]]; then
    TLS_ARGS+=(--cacert "$RECOMMENDATION_LOAD_CA_CERT")
  fi
else
  TLS_ARGS+=(--insecure)
fi

COMMON_ARGS=(
  --proto "$PROTO"
  --import-path "$IMPORT_PATH"
  --call
  --rps "$RPS"
  --duration "$DURATION"
  --format summary
)

run_ghz() {
  local rpc="$1"
  local data="$2"
  ghz "${TLS_ARGS[@]}" "${AUTH_ARGS[@]}" "${COMMON_ARGS[@]}" \
    "$SERVICE.$rpc" \
    --data "$data" \
    "$TARGET"
}

case "$METHOD" in
  profile)
    run_ghz "GetProfileStatus" '{}'
    ;;
  beverage)
    run_ghz "GetBeverageRecommendations" \
      "{\"category\":\"${RECOMMENDATION_LOAD_CATEGORY:-}\",\"limit\":${RECOMMENDATION_LOAD_LIMIT:-5},\"budget_mode\":\"BUDGET_MODE_SOFT\"}"
    ;;
  venue)
    if [[ -z "${RECOMMENDATION_LOAD_SELECTED_BEVERAGE_ID:-}" ]]; then
      echo "RECOMMENDATION_LOAD_SELECTED_BEVERAGE_ID is required for venue load" >&2
      exit 2
    fi
    run_ghz "GetVenueRecommendations" \
      "{\"selected_beverage_id\":\"$RECOMMENDATION_LOAD_SELECTED_BEVERAGE_ID\",\"lat\":${RECOMMENDATION_LOAD_LAT:-37.5001},\"lng\":${RECOMMENDATION_LOAD_LNG:-127.0276},\"radius_m\":${RECOMMENDATION_LOAD_RADIUS_M:-3000},\"limit\":${RECOMMENDATION_LOAD_LIMIT:-3},\"budget_mode\":\"BUDGET_MODE_SOFT\"}"
    ;;
  interaction)
    if [[ "${RECOMMENDATION_LOAD_ALLOW_MUTATION:-0}" != "1" ]]; then
      echo "interaction load mutates recommendation_interactions; set RECOMMENDATION_LOAD_ALLOW_MUTATION=1 with safe test IDs" >&2
      exit 2
    fi
    if [[ -z "${RECOMMENDATION_LOAD_REQUEST_ID:-}" || -z "${RECOMMENDATION_LOAD_RESULT_ID:-}" ]]; then
      echo "RECOMMENDATION_LOAD_REQUEST_ID and RECOMMENDATION_LOAD_RESULT_ID are required" >&2
      exit 2
    fi
    run_ghz "RecordRecommendationEvent" \
      "{\"request_id\":\"$RECOMMENDATION_LOAD_REQUEST_ID\",\"result_id\":\"$RECOMMENDATION_LOAD_RESULT_ID\",\"event_type\":\"RECOMMENDATION_EVENT_TYPE_IMPRESSION\",\"idempotency_key\":\"load-${PROFILE}-${RANDOM}\",\"metadata\":{\"fields\":{\"load_profile\":{\"string_value\":\"$PROFILE\"}}}}"
    ;;
  mixed)
    echo "mixed profile runs profile then beverage. Venue and interaction require explicit IDs."
    "$0" profile
    "$0" beverage
    if [[ -n "${RECOMMENDATION_LOAD_SELECTED_BEVERAGE_ID:-}" ]]; then
      "$0" venue
    fi
    if [[ "${RECOMMENDATION_LOAD_ALLOW_MUTATION:-0}" == "1" ]]; then
      "$0" interaction
    fi
    ;;
  *)
    echo "usage: $0 [profile|beverage|venue|interaction|mixed]" >&2
    exit 2
    ;;
esac
