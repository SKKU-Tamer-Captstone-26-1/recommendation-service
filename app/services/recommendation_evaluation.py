from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.domain.foundation_versions import scoring_v1_payloads
from app.models.enums import ProfileStatus
from app.models.profile import TasteProfileRevision
from app.models.versioning import ScoringConfig
from app.repositories.catalog import BeverageVectorCandidate
from app.services.beverage_import import CanonicalSeedRecord
from app.services.profile_generation import SurveyMapperV1, SurveyProfileInput
from app.services.recommendations import score_beverage_candidate

EVALUATION_VERSION = "drink_evaluation_v1"
EVALUATION_NAMESPACE = uuid.UUID("48a37b12-bf11-55a4-b417-330d3bfb1cb2")


class EvaluationFixtureError(ValueError):
    """Raised when drink evaluation fixtures are malformed."""


@dataclass(frozen=True)
class DrinkEvaluationFixture:
    fixture_id: str
    profile_name: str
    survey_answers: dict[str, Any]
    expected_categories: tuple[str, ...]
    expected_styles: tuple[str, ...]
    positive_catalog_keys: tuple[str, ...]
    negative_catalog_keys: tuple[str, ...]
    expected_reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class RankedDrinkResult:
    rank: int
    catalog_key: str
    category: str
    style: str | None
    final_score: float
    similarity_score: float
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "catalog_key": self.catalog_key,
            "category": self.category,
            "style": self.style,
            "final_score": self.final_score,
            "similarity_score": self.similarity_score,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class FixtureEvaluationResult:
    fixture_id: str
    profile_name: str
    top_k_hit: bool
    category_style_match_rate: float
    negative_violations: tuple[str, ...]
    reason_code_coverage: float
    average_positive_score: float | None
    average_negative_score: float | None
    top_results: tuple[RankedDrinkResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "profile_name": self.profile_name,
            "top_k_hit": self.top_k_hit,
            "category_style_match_rate": self.category_style_match_rate,
            "negative_violations": list(self.negative_violations),
            "reason_code_coverage": self.reason_code_coverage,
            "average_positive_score": self.average_positive_score,
            "average_negative_score": self.average_negative_score,
            "top_results": [result.to_dict() for result in self.top_results],
        }


@dataclass(frozen=True)
class DrinkEvaluationReport:
    generated_at: str
    evaluation_version: str
    scoring_config_version: str
    vector_schema_version: str
    metrics: dict[str, Any]
    fixture_results: tuple[FixtureEvaluationResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "evaluation_version": self.evaluation_version,
            "scoring_config_version": self.scoring_config_version,
            "vector_schema_version": self.vector_schema_version,
            "metrics": self.metrics,
            "fixture_results": [
                result.to_dict() for result in self.fixture_results
            ],
        }


def load_drink_evaluation_fixtures(path: Path) -> tuple[DrinkEvaluationFixture, ...]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise EvaluationFixtureError("evaluation fixture file must be a JSON object")
    fixtures = payload.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        raise EvaluationFixtureError("fixtures must be a non-empty list")
    return tuple(_fixture_from_payload(item) for item in fixtures)


def evaluate_seed_drink_recommendations(
    *,
    records: tuple[CanonicalSeedRecord, ...],
    fixtures: tuple[DrinkEvaluationFixture, ...],
    limit: int = 5,
    generated_at: datetime | None = None,
) -> DrinkEvaluationReport:
    scoring_config = _default_beverage_scoring_config()
    candidates = tuple(
        BeverageVectorCandidate(
            beverage=record.beverage,
            vector=record.vector,
            flavor_profile=record.flavor_profile,
        )
        for record in records
    )
    schema_id = records[0].vector.vector_schema_version_id if records else uuid.uuid4()
    fixture_results = tuple(
        _evaluate_fixture(
            fixture=fixture,
            candidates=candidates,
            scoring_config=scoring_config,
            vector_schema_version_id=schema_id,
            limit=limit,
        )
        for fixture in fixtures
    )
    metrics = _aggregate_metrics(fixture_results)
    return DrinkEvaluationReport(
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        evaluation_version=EVALUATION_VERSION,
        scoring_config_version=scoring_config.version,
        vector_schema_version="taste_v1",
        metrics=metrics,
        fixture_results=fixture_results,
    )


def write_drink_evaluation_report(report: DrinkEvaluationReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )


def _fixture_from_payload(payload: object) -> DrinkEvaluationFixture:
    if not isinstance(payload, dict):
        raise EvaluationFixtureError("fixture must be a JSON object")
    fixture_id = _required_string(payload, "fixture_id")
    profile_name = _required_string(payload, "profile_name")
    survey_answers = payload.get("survey_answers")
    if not isinstance(survey_answers, dict):
        raise EvaluationFixtureError(f"{fixture_id}: survey_answers must be an object")
    return DrinkEvaluationFixture(
        fixture_id=fixture_id,
        profile_name=profile_name,
        survey_answers=survey_answers,
        expected_categories=_string_tuple(payload.get("expected_categories")),
        expected_styles=_string_tuple(payload.get("expected_styles")),
        positive_catalog_keys=_string_tuple(payload.get("positive_catalog_keys")),
        negative_catalog_keys=_string_tuple(payload.get("negative_catalog_keys")),
        expected_reason_codes=_string_tuple(payload.get("expected_reason_codes")),
    )


def _evaluate_fixture(
    *,
    fixture: DrinkEvaluationFixture,
    candidates: tuple[BeverageVectorCandidate, ...],
    scoring_config: ScoringConfig,
    vector_schema_version_id: uuid.UUID,
    limit: int,
) -> FixtureEvaluationResult:
    profile = _profile_from_fixture(fixture, vector_schema_version_id)
    scored = [
        (
            candidate,
            score_beverage_candidate(
                profile=profile,
                candidate=candidate,
                scoring_config=scoring_config,
            ),
        )
        for candidate in candidates
    ]
    ranked = sorted(
        scored,
        key=lambda item: (
            -item[1].final_score,
            -item[1].similarity,
            _catalog_key(item[0]),
        ),
    )
    top_results = tuple(
        RankedDrinkResult(
            rank=index,
            catalog_key=_catalog_key(candidate),
            category=candidate.beverage.category,
            style=_style(candidate),
            final_score=score.final_score,
            similarity_score=score.similarity,
            reason_codes=tuple(score.reason_codes),
        )
        for index, (candidate, score) in enumerate(ranked[:limit], start=1)
    )
    top_keys = {result.catalog_key for result in top_results}
    positives = set(fixture.positive_catalog_keys)
    negatives = set(fixture.negative_catalog_keys)
    category_or_style_matches = [
        result
        for result in top_results
        if result.category in fixture.expected_categories
        or (result.style is not None and result.style in fixture.expected_styles)
    ]
    expected_reasons = set(fixture.expected_reason_codes)
    actual_reasons = {
        reason_code
        for result in top_results
        for reason_code in result.reason_codes
    }
    final_scores_by_key = {
        _catalog_key(candidate): score.final_score for candidate, score in scored
    }
    return FixtureEvaluationResult(
        fixture_id=fixture.fixture_id,
        profile_name=fixture.profile_name,
        top_k_hit=bool(positives & top_keys),
        category_style_match_rate=_ratio(
            len(category_or_style_matches),
            len(top_results),
        ),
        negative_violations=tuple(sorted(negatives & top_keys)),
        reason_code_coverage=_ratio(
            len(expected_reasons & actual_reasons),
            len(expected_reasons),
        ),
        average_positive_score=_average_scores(final_scores_by_key, positives),
        average_negative_score=_average_scores(final_scores_by_key, negatives),
        top_results=top_results,
    )


def _profile_from_fixture(
    fixture: DrinkEvaluationFixture,
    vector_schema_version_id: uuid.UUID,
) -> TasteProfileRevision:
    generated = SurveyMapperV1().map(
        SurveyProfileInput(
            survey_response_id=f"eval_{fixture.fixture_id}",
            external_user_id=f"eval_user_{fixture.fixture_id}",
            survey_version="evaluation_v1",
            response_revision=1,
            completed_at=datetime(2026, 5, 24, tzinfo=UTC),
            answers=fixture.survey_answers,
        ),
    )
    return TasteProfileRevision(
        id=uuid.uuid5(EVALUATION_NAMESPACE, fixture.fixture_id),
        external_user_id=f"eval_user_{fixture.fixture_id}",
        profile_revision=1,
        survey_response_id=f"eval_{fixture.fixture_id}",
        survey_version="evaluation_v1",
        survey_response_revision=1,
        mapper_version_id=uuid.uuid5(EVALUATION_NAMESPACE, "survey_mapper_v1"),
        vector_schema_version_id=vector_schema_version_id,
        taste_vector=generated.taste_vector,
        taste_vector_json=generated.taste_vector_json,
        confidence_json=generated.confidence_json,
        preferred_categories=generated.preferred_categories,
        preferred_keywords=generated.preferred_keywords,
        budget_range=generated.budget_range,
        experience_level=generated.experience_level,
        status=ProfileStatus.ACTIVE.value,
        generated_at=datetime(2026, 5, 24, tzinfo=UTC),
        generation_metadata_json={"evaluation_fixture": fixture.fixture_id},
    )


def _aggregate_metrics(
    fixture_results: tuple[FixtureEvaluationResult, ...],
) -> dict[str, Any]:
    return {
        "fixture_count": len(fixture_results),
        "top_k_hit_rate": _ratio(
            sum(1 for result in fixture_results if result.top_k_hit),
            len(fixture_results),
        ),
        "average_category_style_match_rate": _average(
            result.category_style_match_rate for result in fixture_results
        ),
        "negative_violation_count": sum(
            len(result.negative_violations) for result in fixture_results
        ),
        "average_reason_code_coverage": _average(
            result.reason_code_coverage for result in fixture_results
        ),
        "fixtures_with_positive_score_above_negative": sum(
            1
            for result in fixture_results
            if result.average_positive_score is not None
            and result.average_negative_score is not None
            and result.average_positive_score > result.average_negative_score
        ),
    }


def _default_beverage_scoring_config() -> ScoringConfig:
    payload = next(
        item for item in scoring_v1_payloads() if item["target_type"] == "beverage"
    )
    return ScoringConfig(
        id=uuid.uuid5(EVALUATION_NAMESPACE, "scoring_v1:beverage"),
        name=payload["name"],
        version=payload["version"],
        target_type=payload["target_type"],
        category=payload["category"],
        weights_json=payload["weights_json"],
        reason_code_rules_json=payload["reason_code_rules_json"],
        status=payload["status"],
    )


def _catalog_key(candidate: BeverageVectorCandidate) -> str:
    value = candidate.beverage.metadata_json.get("catalog_key")
    return value if isinstance(value, str) else str(candidate.beverage.id)


def _style(candidate: BeverageVectorCandidate) -> str | None:
    value = candidate.beverage.metadata_json.get("style")
    return value if isinstance(value, str) else None


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise EvaluationFixtureError(f"{key} is required")
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _average_scores(
    scores_by_key: dict[str, float],
    catalog_keys: set[str],
) -> float | None:
    scores = [
        scores_by_key[catalog_key]
        for catalog_key in sorted(catalog_keys)
        if catalog_key in scores_by_key
    ]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 6)


def _average(values) -> float:
    collected = list(values)
    if not collected:
        return 0.0
    return round(sum(collected) / len(collected), 6)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 6)
