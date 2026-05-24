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
    parser.add_argument("--min-fixture-count", type=int, default=0)
    parser.add_argument("--min-category-style-match-rate", type=float, default=0.0)
    parser.add_argument("--max-negative-violations", type=int, default=None)
    parser.add_argument("--min-reason-code-coverage", type=float, default=0.0)
    parser.add_argument("--min-positive-above-negative-rate", type=float, default=0.0)
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
    failures = _threshold_failures(report.metrics, args)
    for failure in failures:
        print(f"threshold_failed {failure}")
    return 1 if failures else 0


def _threshold_failures(
    metrics: dict[str, object],
    args: argparse.Namespace,
) -> list[str]:
    failures: list[str] = []
    if int(metrics["fixture_count"]) < args.min_fixture_count:
        failures.append(
            f"fixture_count={metrics['fixture_count']} "
            f"min={args.min_fixture_count}",
        )
    if float(metrics["top_k_hit_rate"]) < args.min_hit_rate:
        failures.append(
            f"top_k_hit_rate={metrics['top_k_hit_rate']} min={args.min_hit_rate}",
        )
    if (
        args.max_negative_violations is not None
        and int(metrics["negative_violation_count"]) > args.max_negative_violations
    ):
        failures.append(
            "negative_violation_count="
            f"{metrics['negative_violation_count']} "
            f"max={args.max_negative_violations}",
        )
    if (
        float(metrics["average_category_style_match_rate"])
        < args.min_category_style_match_rate
    ):
        failures.append(
            "average_category_style_match_rate="
            f"{metrics['average_category_style_match_rate']} "
            f"min={args.min_category_style_match_rate}",
        )
    if (
        float(metrics["average_reason_code_coverage"])
        < args.min_reason_code_coverage
    ):
        failures.append(
            "average_reason_code_coverage="
            f"{metrics['average_reason_code_coverage']} "
            f"min={args.min_reason_code_coverage}",
        )
    if (
        float(metrics["positive_score_above_negative_rate"])
        < args.min_positive_above_negative_rate
    ):
        failures.append(
            "positive_score_above_negative_rate="
            f"{metrics['positive_score_above_negative_rate']} "
            f"min={args.min_positive_above_negative_rate}",
        )
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
