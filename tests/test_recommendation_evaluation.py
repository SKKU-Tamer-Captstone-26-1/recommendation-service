import uuid
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domain.foundation_versions import SCORING_V3
from app.services.beverage_import import (
    build_canonical_seed_records,
    load_candidate_artifacts,
)
from app.services.recommendation_evaluation import (
    DirectionalFollowupFixture,
    EvaluationFixtureError,
    evaluate_seed_drink_recommendations,
    load_drink_evaluation_fixtures,
)
from app.tools.evaluate_drink_recommendations import _threshold_failures


def test_drink_evaluation_fixtures_load() -> None:
    fixtures = load_drink_evaluation_fixtures(
        Path("data/evaluation/drink_profiles_v1.json"),
    )

    assert len(fixtures) >= 29
    assert fixtures[0].fixture_id
    assert fixtures[0].positive_catalog_keys
    assert sum(len(fixture.directional_followups) for fixture in fixtures) >= 6


def test_drink_evaluation_report_is_deterministic_for_seed_records() -> None:
    records = build_canonical_seed_records(
        artifacts=load_candidate_artifacts(Path("data/beverage")),
        vector_schema_version_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
    )
    fixtures = load_drink_evaluation_fixtures(
        Path("data/evaluation/drink_profiles_v1.json"),
    )

    report = evaluate_seed_drink_recommendations(
        records=records,
        fixtures=fixtures,
        limit=5,
    )

    assert report.metrics["fixture_count"] == len(fixtures)
    assert report.scoring_config_version == SCORING_V3
    assert report.metrics["top_k_hit_rate"] >= 0.95
    assert report.metrics["top_result_positive_hit_rate"] == 1.0
    assert report.metrics["fixtures_missing_top_result_positive"] == []
    assert report.metrics["negative_violation_count"] == 0
    assert report.metrics["average_category_style_match_rate"] >= 0.65
    assert report.metrics["average_reason_code_coverage"] >= 0.95
    assert report.metrics["top_result_reason_hit_rate"] == 1.0
    assert report.metrics["average_top_result_reason_coverage"] >= 0.5
    assert report.metrics["fixtures_missing_top_result_reason"] == []
    assert report.metrics["different_followup_change_rate"] == 1.0
    assert (
        report.metrics["different_followup_style_or_category_change_rate"] >= 0.95
    )
    assert report.metrics["different_followup_missing"] == []
    assert report.metrics["adjacent_followup_change_rate"] == 1.0
    assert report.metrics["adjacent_followup_missing"] == []
    assert report.metrics["adjacent_followup_same_candidate"] == []
    assert report.metrics["budget_sensitivity_low_budget"] == "under_30000"
    assert report.metrics["budget_sensitivity_high_budget"] == "over_200000"
    assert report.metrics["budget_affordable_candidate_count"] >= 20
    assert report.metrics["budget_premium_candidate_count"] >= 2
    assert report.metrics["budget_affordable_score_preference_rate"] == 1.0
    assert report.metrics["budget_premium_score_preference_rate"] == 1.0
    assert report.metrics["budget_affordable_score_preference_failures"] == []
    assert report.metrics["budget_premium_score_preference_failures"] == []
    assert report.metrics["positive_score_above_negative_rate"] == 1.0
    assert report.metrics["positive_score_not_above_negative_failures"] == []
    assert report.metrics["minimum_positive_negative_margin"] > 0
    assert report.metrics["minimum_positive_negative_margin"] >= 0.15
    assert report.metrics["average_positive_negative_margin"] > 0
    assert report.metrics["directional_followup_count"] == 6
    assert report.metrics["directional_followup_score_preference_rate"] == 1.0
    assert report.metrics["directional_followup_score_preference_failures"] == []
    assert report.metrics["directional_followup_direction_count"] == 6
    assert report.metrics["minimum_directional_followups_per_direction"] == 1
    assert report.metrics["minimum_directional_followup_margin"] >= 0.05
    assert report.metrics["average_directional_followup_margin"] > 0
    assert report.metrics["active_category_fixture_coverage"] == 1.0
    assert report.metrics["minimum_fixtures_per_active_category"] >= 2
    assert report.metrics["missing_fixture_categories"] == []
    assert report.metrics["experience_level_fixture_coverage"] == 1.0
    assert report.metrics["minimum_fixtures_per_experience_level"] >= 3
    assert report.metrics["missing_experience_levels"] == []
    assert report.metrics["deployed_budget_range_fixture_coverage"] == 1.0
    assert report.metrics["minimum_fixtures_per_deployed_budget_range"] >= 1
    assert report.metrics["missing_deployed_budget_ranges"] == []
    assert report.metrics["deployed_survey_category_fixture_coverage"] == 1.0
    assert report.metrics["missing_deployed_survey_categories"] == []
    assert (
        report.metrics["deployed_survey_category_trait_fixture_coverage"] == 1.0
    )
    assert report.metrics["missing_deployed_survey_category_trait_tokens"] == []
    assert (
        report.metrics["deployed_survey_flavor_keyword_fixture_coverage"] == 1.0
    )
    assert report.metrics["missing_deployed_survey_flavor_keywords"] == []
    assert len(report.metrics["deployed_survey_categories"]) == 5
    assert len(report.metrics["deployed_survey_category_trait_tokens"]) == 20
    assert len(report.metrics["deployed_survey_flavor_keywords"]) == 9
    assert set(report.metrics["active_catalog_categories"]) == {
        "beer",
        "brandy_cognac",
        "cocktail",
        "gin",
        "liqueur",
        "rum",
        "sake_shochu",
        "tequila_mezcal",
        "traditional_korean_alcohol",
        "vodka",
        "whiskey",
        "wine",
    }
    assert set(report.metrics["deployed_budget_ranges"]) == {
        "under_30000",
        "30000_100000",
        "100000_200000",
        "over_200000",
    }
    assert all(result.top_results for result in report.fixture_results)


def test_drink_evaluation_reports_missing_active_category_fixture_coverage() -> None:
    records = build_canonical_seed_records(
        artifacts=load_candidate_artifacts(Path("data/beverage")),
        vector_schema_version_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
    )
    fixtures = load_drink_evaluation_fixtures(
        Path("data/evaluation/drink_profiles_v1.json"),
    )

    report = evaluate_seed_drink_recommendations(
        records=records,
        fixtures=fixtures[:1],
        limit=5,
    )

    assert report.metrics["active_category_fixture_coverage"] < 1.0
    assert report.metrics["minimum_fixtures_per_active_category"] == 0
    assert "beer" in report.metrics["missing_fixture_categories"]
    assert report.metrics["experience_level_fixture_coverage"] < 1.0
    assert "expert" in report.metrics["missing_experience_levels"]
    assert report.metrics["deployed_budget_range_fixture_coverage"] < 1.0
    assert "over_200000" in report.metrics["missing_deployed_budget_ranges"]
    assert report.metrics["deployed_survey_category_fixture_coverage"] < 1.0
    assert "cognac" in report.metrics["missing_deployed_survey_categories"]
    assert (
        report.metrics["deployed_survey_category_trait_fixture_coverage"] < 1.0
    )
    assert "beer:sour_wild" in report.metrics[
        "missing_deployed_survey_category_trait_tokens"
    ]
    assert (
        report.metrics["deployed_survey_flavor_keyword_fixture_coverage"] < 1.0
    )
    assert "herb_mint" in report.metrics[
        "missing_deployed_survey_flavor_keywords"
    ]


def test_drink_evaluation_reports_missing_top_result_reason() -> None:
    records = build_canonical_seed_records(
        artifacts=load_candidate_artifacts(Path("data/beverage")),
        vector_schema_version_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
    )
    fixture = load_drink_evaluation_fixtures(
        Path("data/evaluation/drink_profiles_v1.json"),
    )[0]

    report = evaluate_seed_drink_recommendations(
        records=records,
        fixtures=(
            replace(
                fixture,
                expected_reason_codes=("IMPOSSIBLE_REASON_FOR_TEST",),
            ),
        ),
        limit=5,
    )

    assert report.metrics["top_result_reason_hit_rate"] == 0.0
    assert report.metrics["average_top_result_reason_coverage"] == 0.0
    assert report.metrics["fixtures_missing_top_result_reason"] == [
        fixture.fixture_id,
    ]
    result = report.fixture_results[0]
    assert result.top_result_reason_hit is False
    assert result.top_result_missing_reason_codes == (
        "IMPOSSIBLE_REASON_FOR_TEST",
    )


def test_drink_evaluation_reports_missing_diversity_followups() -> None:
    records = build_canonical_seed_records(
        artifacts=load_candidate_artifacts(Path("data/beverage")),
        vector_schema_version_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
    )
    fixture = load_drink_evaluation_fixtures(
        Path("data/evaluation/drink_profiles_v1.json"),
    )[0]

    report = evaluate_seed_drink_recommendations(
        records=records[:1],
        fixtures=(fixture,),
        limit=5,
    )

    assert report.metrics["different_followup_change_rate"] == 0.0
    assert report.metrics["different_followup_style_or_category_change_rate"] == 0.0
    assert report.metrics["different_followup_missing"] == [fixture.fixture_id]
    assert report.metrics["adjacent_followup_change_rate"] == 0.0
    assert report.metrics["adjacent_followup_missing"] == [fixture.fixture_id]
    assert report.metrics["adjacent_followup_same_candidate"] == []
    diversity_followups = report.fixture_results[0].diversity_followups
    assert diversity_followups["different"]["catalog_key"] is None
    assert diversity_followups["adjacent"]["catalog_key"] is None


def test_drink_evaluation_reports_insufficient_budget_sensitivity_candidates() -> None:
    records = build_canonical_seed_records(
        artifacts=load_candidate_artifacts(Path("data/beverage")),
        vector_schema_version_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
    )
    fixture = load_drink_evaluation_fixtures(
        Path("data/evaluation/drink_profiles_v1.json"),
    )[0]

    report = evaluate_seed_drink_recommendations(
        records=records[:1],
        fixtures=(fixture,),
        limit=5,
    )

    assert report.metrics["budget_affordable_candidate_count"] == 1
    assert report.metrics["budget_premium_candidate_count"] == 0
    assert report.metrics["budget_affordable_score_preference_rate"] == 1.0
    assert report.metrics["budget_premium_score_preference_rate"] == 0.0
    assert report.metrics["budget_premium_score_preference_failures"] == []


def test_drink_evaluation_reports_positive_negative_score_failures() -> None:
    records = build_canonical_seed_records(
        artifacts=load_candidate_artifacts(Path("data/beverage")),
        vector_schema_version_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
    )
    fixture = load_drink_evaluation_fixtures(
        Path("data/evaluation/drink_profiles_v1.json"),
    )[0]

    report = evaluate_seed_drink_recommendations(
        records=records,
        fixtures=(
            replace(
                fixture,
                positive_catalog_keys=fixture.negative_catalog_keys,
                negative_catalog_keys=fixture.positive_catalog_keys,
            ),
        ),
        limit=5,
    )

    assert report.metrics["positive_score_above_negative_rate"] == 0.0
    assert report.metrics["fixtures_with_positive_score_above_negative"] == 0
    assert report.metrics["positive_score_not_above_negative_failures"] == [
        {
            "fixture_id": fixture.fixture_id,
            "profile_name": fixture.profile_name,
            "average_positive_score": report.fixture_results[
                0
            ].average_positive_score,
            "average_negative_score": report.fixture_results[
                0
            ].average_negative_score,
            "positive_negative_margin": report.fixture_results[
                0
            ].positive_negative_margin,
        },
    ]
    assert report.fixture_results[0].positive_score_above_negative is False
    assert report.fixture_results[0].positive_negative_margin < 0


def test_drink_evaluation_reports_directional_followup_failures() -> None:
    records = build_canonical_seed_records(
        artifacts=load_candidate_artifacts(Path("data/beverage")),
        vector_schema_version_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
    )
    fixture = load_drink_evaluation_fixtures(
        Path("data/evaluation/drink_profiles_v1.json"),
    )[0]

    report = evaluate_seed_drink_recommendations(
        records=records,
        fixtures=(
            replace(
                fixture,
                directional_followups=(
                    DirectionalFollowupFixture(
                        direction="inverted_direction_for_test",
                        survey_answer_overrides={
                            "categories": ["whiskey"],
                            "category_traits": {"whiskey": ["peat_character"]},
                            "global_keywords": ["smoky_peat"],
                        },
                        positive_catalog_keys=("whiskey.buffalo_trace_bourbon",),
                        negative_catalog_keys=("whiskey.laphroaig_10_year_old",),
                    ),
                ),
            ),
        ),
        limit=5,
    )

    assert report.metrics["directional_followup_count"] == 1
    assert report.metrics["directional_followup_score_preference_rate"] == 0.0
    assert report.metrics["directional_followup_direction_count"] == 1
    assert report.metrics["directional_followup_score_preference_failures"] == [
        {
            "fixture_id": fixture.fixture_id,
            "profile_name": fixture.profile_name,
            "direction": "inverted_direction_for_test",
            "positive_catalog_keys": ["whiskey.buffalo_trace_bourbon"],
            "negative_catalog_keys": ["whiskey.laphroaig_10_year_old"],
            "average_positive_score": report.fixture_results[
                0
            ].directional_followups[0].average_positive_score,
            "average_negative_score": report.fixture_results[
                0
            ].directional_followups[0].average_negative_score,
            "positive_negative_margin": report.fixture_results[
                0
            ].directional_followups[0].positive_negative_margin,
            "missing_positive_catalog_keys": [],
            "missing_negative_catalog_keys": [],
            "top_results": [
                result.to_dict()
                for result in report.fixture_results[0]
                .directional_followups[0]
                .top_results
            ],
        },
    ]
    assert report.metrics["minimum_directional_followup_margin"] < 0
    assert report.metrics["average_directional_followup_margin"] < 0
    assert report.fixture_results[0].directional_followups[
        0
    ].positive_score_above_negative is False
    assert (
        report.fixture_results[0].directional_followups[0].positive_negative_margin
        < 0
    )


def test_drink_evaluation_thresholds_fail_on_weak_margins() -> None:
    metrics = {
        "fixture_count": 29,
        "top_k_hit_rate": 1.0,
        "top_result_positive_hit_rate": 0.5,
        "negative_violation_count": 0,
        "average_category_style_match_rate": 1.0,
        "average_reason_code_coverage": 1.0,
        "top_result_reason_hit_rate": 1.0,
        "average_top_result_reason_coverage": 1.0,
        "different_followup_change_rate": 1.0,
        "different_followup_style_or_category_change_rate": 1.0,
        "adjacent_followup_change_rate": 1.0,
        "budget_affordable_candidate_count": 20,
        "budget_premium_candidate_count": 2,
        "budget_affordable_score_preference_rate": 1.0,
        "budget_premium_score_preference_rate": 1.0,
        "positive_score_above_negative_rate": 1.0,
        "minimum_positive_negative_margin": 0.01,
        "directional_followup_count": 6,
        "directional_followup_score_preference_rate": 1.0,
        "directional_followup_direction_count": 6,
        "minimum_directional_followup_margin": 0.01,
        "active_category_fixture_coverage": 1.0,
        "minimum_fixtures_per_active_category": 2,
        "experience_level_fixture_coverage": 1.0,
        "minimum_fixtures_per_experience_level": 3,
        "deployed_budget_range_fixture_coverage": 1.0,
        "minimum_fixtures_per_deployed_budget_range": 1,
        "deployed_survey_category_fixture_coverage": 1.0,
        "deployed_survey_category_trait_fixture_coverage": 1.0,
        "deployed_survey_flavor_keyword_fixture_coverage": 1.0,
    }

    failures = _threshold_failures(
        metrics,
        SimpleNamespace(
            min_fixture_count=29,
            min_hit_rate=0.95,
            min_top_result_positive_hit_rate=1.0,
            max_negative_violations=0,
            min_category_style_match_rate=0.65,
            min_reason_code_coverage=0.95,
            min_top_result_reason_hit_rate=1.0,
            min_average_top_result_reason_coverage=0.5,
            min_different_followup_change_rate=1.0,
            min_different_followup_style_or_category_change_rate=0.95,
            min_adjacent_followup_change_rate=1.0,
            min_budget_affordable_candidate_count=20,
            min_budget_premium_candidate_count=2,
            min_budget_affordable_score_preference_rate=1.0,
            min_budget_premium_score_preference_rate=1.0,
            min_positive_above_negative_rate=1.0,
            min_positive_negative_margin=0.15,
            min_directional_followup_count=6,
            min_directional_followup_score_preference_rate=1.0,
            min_directional_followup_direction_count=6,
            min_directional_followup_margin=0.05,
            min_active_category_coverage=1.0,
            min_fixtures_per_active_category=2,
            min_experience_level_coverage=1.0,
            min_fixtures_per_experience_level=3,
            min_deployed_budget_coverage=1.0,
            min_fixtures_per_deployed_budget=1,
            min_deployed_survey_category_coverage=1.0,
            min_deployed_survey_category_trait_coverage=1.0,
            min_deployed_survey_flavor_keyword_coverage=1.0,
        ),
    )

    assert failures == [
        "top_result_positive_hit_rate=0.5 min=1.0",
        "minimum_positive_negative_margin=0.01 min=0.15",
        "minimum_directional_followup_margin=0.01 min=0.05",
    ]


def test_drink_evaluation_rejects_invalid_fixture_file(tmp_path: Path) -> None:
    fixture_path = tmp_path / "invalid.json"
    fixture_path.write_text('{"fixtures": []}')

    with pytest.raises(EvaluationFixtureError):
        load_drink_evaluation_fixtures(fixture_path)
