"""Evaluate drink-only recommendation precision against local fixtures."""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from app.domain.foundation_versions import SCORING_V3
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
    parser.add_argument("--scoring-config-version", default=SCORING_V3)
    parser.add_argument("--min-hit-rate", type=float, default=0.0)
    parser.add_argument("--min-top-result-positive-hit-rate", type=float, default=0.0)
    parser.add_argument("--min-fixture-count", type=int, default=0)
    parser.add_argument("--min-category-style-match-rate", type=float, default=0.0)
    parser.add_argument("--max-negative-violations", type=int, default=None)
    parser.add_argument("--min-reason-code-coverage", type=float, default=0.0)
    parser.add_argument("--min-top-result-reason-hit-rate", type=float, default=0.0)
    parser.add_argument(
        "--min-average-top-result-reason-coverage",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-different-followup-change-rate", type=float, default=0.0)
    parser.add_argument(
        "--min-different-followup-style-or-category-change-rate",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-adjacent-followup-change-rate", type=float, default=0.0)
    parser.add_argument("--min-budget-affordable-candidate-count", type=int, default=0)
    parser.add_argument("--min-budget-premium-candidate-count", type=int, default=0)
    parser.add_argument(
        "--min-budget-affordable-score-preference-rate",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-budget-premium-score-preference-rate",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-positive-above-negative-rate", type=float, default=0.0)
    parser.add_argument("--min-positive-negative-margin", type=float, default=0.0)
    parser.add_argument("--min-directional-followup-count", type=int, default=0)
    parser.add_argument(
        "--min-directional-followup-score-preference-rate",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-directional-followup-direction-count",
        type=int,
        default=0,
    )
    parser.add_argument("--min-directional-followup-margin", type=float, default=0.0)
    parser.add_argument("--min-active-category-coverage", type=float, default=0.0)
    parser.add_argument("--min-fixtures-per-active-category", type=int, default=0)
    parser.add_argument("--min-experience-level-coverage", type=float, default=0.0)
    parser.add_argument("--min-fixtures-per-experience-level", type=int, default=0)
    parser.add_argument("--min-deployed-budget-coverage", type=float, default=0.0)
    parser.add_argument("--min-fixtures-per-deployed-budget", type=int, default=0)
    parser.add_argument(
        "--min-deployed-survey-category-coverage",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-deployed-survey-category-trait-coverage",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-deployed-survey-flavor-keyword-coverage",
        type=float,
        default=0.0,
    )
    args = parser.parse_args()

    records = build_canonical_seed_records(
        artifacts=load_candidate_artifacts(args.data_dir),
        vector_schema_version_id=DEFAULT_SCHEMA_ID,
    )
    report = evaluate_seed_drink_recommendations(
        records=records,
        fixtures=load_drink_evaluation_fixtures(args.fixtures),
        limit=args.limit,
        scoring_config_version=args.scoring_config_version,
    )
    write_drink_evaluation_report(report, args.report)
    hit_rate = float(report.metrics["top_k_hit_rate"])
    print(
        "drink recommendation evaluation "
        f"scoring={report.scoring_config_version} "
        f"fixtures={report.metrics['fixture_count']} "
        f"top_k_hit_rate={hit_rate} "
        f"top_result_positive_hit_rate="
        f"{report.metrics['top_result_positive_hit_rate']} "
        f"active_category_fixture_coverage="
        f"{report.metrics['active_category_fixture_coverage']} "
        f"experience_level_fixture_coverage="
        f"{report.metrics['experience_level_fixture_coverage']} "
        f"deployed_budget_range_fixture_coverage="
        f"{report.metrics['deployed_budget_range_fixture_coverage']} "
        f"deployed_survey_category_fixture_coverage="
        f"{report.metrics['deployed_survey_category_fixture_coverage']} "
        f"deployed_survey_category_trait_fixture_coverage="
        f"{report.metrics['deployed_survey_category_trait_fixture_coverage']} "
        f"deployed_survey_flavor_keyword_fixture_coverage="
        f"{report.metrics['deployed_survey_flavor_keyword_fixture_coverage']} "
        f"top_result_reason_hit_rate="
        f"{report.metrics['top_result_reason_hit_rate']} "
        f"different_followup_change_rate="
        f"{report.metrics['different_followup_change_rate']} "
        f"adjacent_followup_change_rate="
        f"{report.metrics['adjacent_followup_change_rate']} "
        f"budget_affordable_score_preference_rate="
        f"{report.metrics['budget_affordable_score_preference_rate']} "
        f"budget_premium_score_preference_rate="
        f"{report.metrics['budget_premium_score_preference_rate']} "
        f"positive_score_above_negative_rate="
        f"{report.metrics['positive_score_above_negative_rate']} "
        f"minimum_positive_negative_margin="
        f"{report.metrics['minimum_positive_negative_margin']} "
        f"directional_followup_count="
        f"{report.metrics['directional_followup_count']} "
        f"directional_followup_score_preference_rate="
        f"{report.metrics['directional_followup_score_preference_rate']} "
        f"directional_followup_direction_count="
        f"{report.metrics['directional_followup_direction_count']} "
        f"minimum_directional_followup_margin="
        f"{report.metrics['minimum_directional_followup_margin']} "
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
        float(metrics["top_result_positive_hit_rate"])
        < args.min_top_result_positive_hit_rate
    ):
        failures.append(
            "top_result_positive_hit_rate="
            f"{metrics['top_result_positive_hit_rate']} "
            f"min={args.min_top_result_positive_hit_rate}",
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
        float(metrics["top_result_reason_hit_rate"])
        < args.min_top_result_reason_hit_rate
    ):
        failures.append(
            "top_result_reason_hit_rate="
            f"{metrics['top_result_reason_hit_rate']} "
            f"min={args.min_top_result_reason_hit_rate}",
        )
    if (
        float(metrics["average_top_result_reason_coverage"])
        < args.min_average_top_result_reason_coverage
    ):
        failures.append(
            "average_top_result_reason_coverage="
            f"{metrics['average_top_result_reason_coverage']} "
            f"min={args.min_average_top_result_reason_coverage}",
        )
    if (
        float(metrics["different_followup_change_rate"])
        < args.min_different_followup_change_rate
    ):
        failures.append(
            "different_followup_change_rate="
            f"{metrics['different_followup_change_rate']} "
            f"min={args.min_different_followup_change_rate}",
        )
    if (
        float(metrics["different_followup_style_or_category_change_rate"])
        < args.min_different_followup_style_or_category_change_rate
    ):
        failures.append(
            "different_followup_style_or_category_change_rate="
            f"{metrics['different_followup_style_or_category_change_rate']} "
            f"min={args.min_different_followup_style_or_category_change_rate}",
        )
    if (
        float(metrics["adjacent_followup_change_rate"])
        < args.min_adjacent_followup_change_rate
    ):
        failures.append(
            "adjacent_followup_change_rate="
            f"{metrics['adjacent_followup_change_rate']} "
            f"min={args.min_adjacent_followup_change_rate}",
        )
    if (
        int(metrics["budget_affordable_candidate_count"])
        < args.min_budget_affordable_candidate_count
    ):
        failures.append(
            "budget_affordable_candidate_count="
            f"{metrics['budget_affordable_candidate_count']} "
            f"min={args.min_budget_affordable_candidate_count}",
        )
    if (
        int(metrics["budget_premium_candidate_count"])
        < args.min_budget_premium_candidate_count
    ):
        failures.append(
            "budget_premium_candidate_count="
            f"{metrics['budget_premium_candidate_count']} "
            f"min={args.min_budget_premium_candidate_count}",
        )
    if (
        float(metrics["budget_affordable_score_preference_rate"])
        < args.min_budget_affordable_score_preference_rate
    ):
        failures.append(
            "budget_affordable_score_preference_rate="
            f"{metrics['budget_affordable_score_preference_rate']} "
            f"min={args.min_budget_affordable_score_preference_rate}",
        )
    if (
        float(metrics["budget_premium_score_preference_rate"])
        < args.min_budget_premium_score_preference_rate
    ):
        failures.append(
            "budget_premium_score_preference_rate="
            f"{metrics['budget_premium_score_preference_rate']} "
            f"min={args.min_budget_premium_score_preference_rate}",
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
    if (
        _optional_float(metrics["minimum_positive_negative_margin"])
        < args.min_positive_negative_margin
    ):
        failures.append(
            "minimum_positive_negative_margin="
            f"{metrics['minimum_positive_negative_margin']} "
            f"min={args.min_positive_negative_margin}",
        )
    if int(metrics["directional_followup_count"]) < args.min_directional_followup_count:
        failures.append(
            "directional_followup_count="
            f"{metrics['directional_followup_count']} "
            f"min={args.min_directional_followup_count}",
        )
    if (
        float(metrics["directional_followup_score_preference_rate"])
        < args.min_directional_followup_score_preference_rate
    ):
        failures.append(
            "directional_followup_score_preference_rate="
            f"{metrics['directional_followup_score_preference_rate']} "
            f"min={args.min_directional_followup_score_preference_rate}",
        )
    if (
        int(metrics["directional_followup_direction_count"])
        < args.min_directional_followup_direction_count
    ):
        failures.append(
            "directional_followup_direction_count="
            f"{metrics['directional_followup_direction_count']} "
            f"min={args.min_directional_followup_direction_count}",
        )
    if (
        _optional_float(metrics["minimum_directional_followup_margin"])
        < args.min_directional_followup_margin
    ):
        failures.append(
            "minimum_directional_followup_margin="
            f"{metrics['minimum_directional_followup_margin']} "
            f"min={args.min_directional_followup_margin}",
        )
    if (
        float(metrics["active_category_fixture_coverage"])
        < args.min_active_category_coverage
    ):
        failures.append(
            "active_category_fixture_coverage="
            f"{metrics['active_category_fixture_coverage']} "
            f"min={args.min_active_category_coverage}",
        )
    if (
        int(metrics["minimum_fixtures_per_active_category"])
        < args.min_fixtures_per_active_category
    ):
        failures.append(
            "minimum_fixtures_per_active_category="
            f"{metrics['minimum_fixtures_per_active_category']} "
            f"min={args.min_fixtures_per_active_category}",
        )
    if (
        float(metrics["experience_level_fixture_coverage"])
        < args.min_experience_level_coverage
    ):
        failures.append(
            "experience_level_fixture_coverage="
            f"{metrics['experience_level_fixture_coverage']} "
            f"min={args.min_experience_level_coverage}",
        )
    if (
        int(metrics["minimum_fixtures_per_experience_level"])
        < args.min_fixtures_per_experience_level
    ):
        failures.append(
            "minimum_fixtures_per_experience_level="
            f"{metrics['minimum_fixtures_per_experience_level']} "
            f"min={args.min_fixtures_per_experience_level}",
        )
    if (
        float(metrics["deployed_budget_range_fixture_coverage"])
        < args.min_deployed_budget_coverage
    ):
        failures.append(
            "deployed_budget_range_fixture_coverage="
            f"{metrics['deployed_budget_range_fixture_coverage']} "
            f"min={args.min_deployed_budget_coverage}",
        )
    if (
        int(metrics["minimum_fixtures_per_deployed_budget_range"])
        < args.min_fixtures_per_deployed_budget
    ):
        failures.append(
            "minimum_fixtures_per_deployed_budget_range="
            f"{metrics['minimum_fixtures_per_deployed_budget_range']} "
            f"min={args.min_fixtures_per_deployed_budget}",
        )
    if (
        float(metrics["deployed_survey_category_fixture_coverage"])
        < args.min_deployed_survey_category_coverage
    ):
        failures.append(
            "deployed_survey_category_fixture_coverage="
            f"{metrics['deployed_survey_category_fixture_coverage']} "
            f"min={args.min_deployed_survey_category_coverage}",
        )
    if (
        float(metrics["deployed_survey_category_trait_fixture_coverage"])
        < args.min_deployed_survey_category_trait_coverage
    ):
        failures.append(
            "deployed_survey_category_trait_fixture_coverage="
            f"{metrics['deployed_survey_category_trait_fixture_coverage']} "
            f"min={args.min_deployed_survey_category_trait_coverage}",
        )
    if (
        float(metrics["deployed_survey_flavor_keyword_fixture_coverage"])
        < args.min_deployed_survey_flavor_keyword_coverage
    ):
        failures.append(
            "deployed_survey_flavor_keyword_fixture_coverage="
            f"{metrics['deployed_survey_flavor_keyword_fixture_coverage']} "
            f"min={args.min_deployed_survey_flavor_keyword_coverage}",
        )
    return failures


def _optional_float(value: object) -> float:
    if value is None:
        return 0.0
    return float(value)


if __name__ == "__main__":
    raise SystemExit(main())
