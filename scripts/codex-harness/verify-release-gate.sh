#!/usr/bin/env bash
set -euo pipefail

REPORT_DIR="${REPORT_DIR:-/private/tmp/recommendation-release-gate}"
mkdir -p "$REPORT_DIR"

python3 -m pytest -q
python3 -m ruff check .
python3 -m compileall -q app tests
git diff --check

python3 -m app.tools.beverage_catalog_audit \
  --report "$REPORT_DIR/beverage_catalog_audit.json"

python3 -m app.tools.evaluate_drink_recommendations \
  --report "$REPORT_DIR/drink_recommendation_evaluation.json" \
  --min-fixture-count 20 \
  --min-hit-rate 0.85 \
  --max-negative-violations 0 \
  --min-category-style-match-rate 0.65 \
  --min-reason-code-coverage 0.95 \
  --min-positive-above-negative-rate 0.9

rg -n \
  "survey.*database|map.*database|survey_db|map_db|SELECT .*survey|SELECT .*map|direct.*survey|direct.*map" \
  app tests && {
    echo "boundary scan failed: direct cross-service DB reference found"
    exit 1
  }

if [[ "${RUN_DB_SMOKE:-0}" == "1" ]]; then
  python3 -m alembic upgrade head
  python3 -m app.tools.operational_metrics_smoke
fi

if [[ "${RUN_QDRANT_SMOKE:-0}" == "1" ]]; then
  python3 -m app.tools.beverage_import --stage --promote-seed
  python3 -m app.tools.beverage_import --promote-seed
  python3 -m app.tools.beverage_catalog_audit \
    --database \
    --report "$REPORT_DIR/beverage_catalog_audit_database.json"
  python3 -m app.tools.qdrant_rebuild \
    --owner-type beverage_item \
    --recreate
  python3 -m app.tools.qdrant_index \
    --owner-type beverage_item
  python3 -m app.tools.qdrant_index_smoke \
    --owner-type beverage_item
  python3 -m app.tools.beverage_recommendation_smoke
fi

if [[ "${RUN_SYNC_SMOKE:-0}" == "1" ]]; then
  python3 -m app.tools.beverage_import --stage --promote-seed
  python3 -m app.tools.survey_sync_smoke
  python3 -m app.tools.venue_recommendation_smoke
fi

if [[ "${RUN_DEPLOYED_SMOKE:-0}" == "1" ]]; then
  python3 -m app.tools.deployed_smoke --mode all
fi

echo "release gate passed reports=$REPORT_DIR"
