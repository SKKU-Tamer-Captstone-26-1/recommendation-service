import uuid
from pathlib import Path

import pytest

from app.services.beverage_import import (
    build_canonical_seed_records,
    load_candidate_artifacts,
)
from app.services.recommendation_evaluation import (
    EvaluationFixtureError,
    evaluate_seed_drink_recommendations,
    load_drink_evaluation_fixtures,
)


def test_drink_evaluation_fixtures_load() -> None:
    fixtures = load_drink_evaluation_fixtures(
        Path("data/evaluation/drink_profiles_v1.json"),
    )

    assert len(fixtures) >= 20
    assert fixtures[0].fixture_id
    assert fixtures[0].positive_catalog_keys


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
    assert report.metrics["top_k_hit_rate"] >= 0.85
    assert report.metrics["negative_violation_count"] == 0
    assert report.metrics["average_category_style_match_rate"] >= 0.65
    assert report.metrics["average_reason_code_coverage"] >= 0.95
    assert report.metrics["positive_score_above_negative_rate"] >= 0.9
    assert all(result.top_results for result in report.fixture_results)


def test_drink_evaluation_rejects_invalid_fixture_file(tmp_path: Path) -> None:
    fixture_path = tmp_path / "invalid.json"
    fixture_path.write_text('{"fixtures": []}')

    with pytest.raises(EvaluationFixtureError):
        load_drink_evaluation_fixtures(fixture_path)
