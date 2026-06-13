#!/usr/bin/env bash
set -euo pipefail

REPORT_DIR="${REPORT_DIR:-/private/tmp/recommendation-release-gate}"
mkdir -p "$REPORT_DIR"

python3 -m pytest -q
python3 -m ruff check .
python3 -m compileall -q app tests
git diff --check

python3 -m app.tools.survey_mapper_audit \
  --report "$REPORT_DIR/survey_mapper_audit.json"

python3 -m app.tools.beverage_catalog_audit \
  --report "$REPORT_DIR/beverage_catalog_audit.json"

python3 -m app.tools.evaluate_drink_recommendations \
  --report "$REPORT_DIR/drink_recommendation_evaluation.json" \
  --scoring-config-version scoring_v3 \
  --min-fixture-count 29 \
  --min-hit-rate 0.95 \
  --min-top-result-positive-hit-rate 1.0 \
  --max-negative-violations 0 \
  --min-category-style-match-rate 0.65 \
  --min-reason-code-coverage 0.95 \
  --min-top-result-reason-hit-rate 1.0 \
  --min-average-top-result-reason-coverage 0.5 \
  --min-different-followup-change-rate 1.0 \
  --min-different-followup-style-or-category-change-rate 0.95 \
  --min-adjacent-followup-change-rate 1.0 \
  --min-budget-affordable-candidate-count 20 \
  --min-budget-premium-candidate-count 2 \
  --min-budget-affordable-score-preference-rate 1.0 \
  --min-budget-premium-score-preference-rate 1.0 \
  --min-positive-above-negative-rate 1.0 \
  --min-positive-negative-margin 0.15 \
  --min-directional-followup-count 6 \
  --min-directional-followup-score-preference-rate 1.0 \
  --min-directional-followup-direction-count 6 \
  --min-directional-followup-margin 0.05 \
  --min-active-category-coverage 1.0 \
  --min-fixtures-per-active-category 2 \
  --min-experience-level-coverage 1.0 \
  --min-fixtures-per-experience-level 3 \
  --min-deployed-budget-coverage 1.0 \
  --min-fixtures-per-deployed-budget 1 \
  --min-deployed-survey-category-coverage 1.0 \
  --min-deployed-survey-category-trait-coverage 1.0 \
  --min-deployed-survey-flavor-keyword-coverage 1.0

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
