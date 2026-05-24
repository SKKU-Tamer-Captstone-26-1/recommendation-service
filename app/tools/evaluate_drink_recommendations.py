"""Evaluate drink-only recommendation precision against local fixtures."""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from app.services.beverage_import import (
    build_canonical_seed_records,
    load_candidate_artifacts,
)
from app.services.recommendation_evaluation import (
    evaluate_seed_drink_recommendations,
    load_drink_evaluation_fixtures,
    write_drink_evaluation_report,
)

DEFAULT_SCHEMA_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data/beverage"))
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("data/evaluation/drink_profiles_v1.json"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/drink_recommendation_evaluation.json"),
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--min-hit-rate", type=float, default=0.0)
    args = parser.parse_args()

    records = build_canonical_seed_records(
        artifacts=load_candidate_artifacts(args.data_dir),
        vector_schema_version_id=DEFAULT_SCHEMA_ID,
    )
    report = evaluate_seed_drink_recommendations(
        records=records,
        fixtures=load_drink_evaluation_fixtures(args.fixtures),
        limit=args.limit,
    )
    write_drink_evaluation_report(report, args.report)
    hit_rate = float(report.metrics["top_k_hit_rate"])
    print(
        "drink recommendation evaluation "
        f"fixtures={report.metrics['fixture_count']} "
        f"top_k_hit_rate={hit_rate} "
        f"negative_violations={report.metrics['negative_violation_count']} "
        f"report={args.report}",
    )
    return 1 if hit_rate < args.min_hit_rate else 0


if __name__ == "__main__":
    raise SystemExit(main())
