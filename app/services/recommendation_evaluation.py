from __future__ import annotations

import json
import uuid
from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.domain.foundation_versions import (
    SCORING_V1,
    SCORING_V2,
    SCORING_V3,
    SURVEY_MAPPER_V1_1,
    scoring_v1_payloads,
    scoring_v2_payloads,
    scoring_v3_payloads,
)
from app.models.enums import ProfileStatus
from app.models.profile import TasteProfileRevision
from app.models.versioning import ScoringConfig
from app.repositories.catalog import BeverageVectorCandidate
from app.services.beverage_import import CanonicalSeedRecord
from app.services.profile_generation import (
    DEPLOYED_SURVEY_BUDGET_RANGES,
    DEPLOYED_SURVEY_CATEGORIES,
    DEPLOYED_SURVEY_CATEGORY_TRAITS,
    DEPLOYED_SURVEY_FLAVOR_KEYWORDS,
    DEPLOYED_SURVEY_LEVELS,
    SurveyMapperV1,
    SurveyProfileInput,
    canonicalize_survey_budget_range,
)
from app.services.recommendations import (
    BEVERAGE_DIVERSITY_ADJACENT,
    BEVERAGE_DIVERSITY_DIFFERENT,
    _beverage_exclusion_context,
    _select_beverage_recommendations,
    score_beverage_candidate,
)

EVALUATION_VERSION = "drink_evaluation_v1"
EVALUATION_NAMESPACE = uuid.UUID("48a37b12-bf11-55a4-b417-330d3bfb1cb2")
BUDGET_SENSITIVITY_LOW_BUDGET = "under_30000"
BUDGET_SENSITIVITY_HIGH_BUDGET = "over_200000"
BUDGET_SENSITIVITY_AFFORDABLE_CEILING_KRW = 30_000
BUDGET_SENSITIVITY_PREMIUM_FLOOR_KRW = 200_000


class EvaluationFixtureError(ValueError):
    """Raised when drink evaluation fixtures are malformed."""


@dataclass(frozen=True)
class DirectionalFollowupFixture:
    direction: str
    survey_answer_overrides: dict[str, Any]
    positive_catalog_keys: tuple[str, ...]
    negative_catalog_keys: tuple[str, ...]


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
    directional_followups: tuple[DirectionalFollowupFixture, ...]


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
class DirectionalFollowupEvaluation:
    direction: str
    positive_catalog_keys: tuple[str, ...]
    negative_catalog_keys: tuple[str, ...]
    average_positive_score: float | None
    average_negative_score: float | None
    positive_score_above_negative: bool
    positive_negative_margin: float | None
    missing_positive_catalog_keys: tuple[str, ...]
    missing_negative_catalog_keys: tuple[str, ...]
    top_results: tuple[RankedDrinkResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "positive_catalog_keys": list(self.positive_catalog_keys),
            "negative_catalog_keys": list(self.negative_catalog_keys),
            "average_positive_score": self.average_positive_score,
            "average_negative_score": self.average_negative_score,
            "positive_score_above_negative": self.positive_score_above_negative,
            "positive_negative_margin": self.positive_negative_margin,
            "missing_positive_catalog_keys": list(self.missing_positive_catalog_keys),
            "missing_negative_catalog_keys": list(self.missing_negative_catalog_keys),
            "top_results": [result.to_dict() for result in self.top_results],
        }


@dataclass(frozen=True)
class FixtureEvaluationResult:
    fixture_id: str
    profile_name: str
    top_k_hit: bool
    top_result_positive_hit: bool
    top_result_catalog_key: str | None
    category_style_match_rate: float
    negative_violations: tuple[str, ...]
    reason_code_coverage: float
    top_result_reason_hit: bool
    top_result_reason_coverage: float
    top_result_missing_reason_codes: tuple[str, ...]
    diversity_followups: dict[str, Any]
    directional_followups: tuple[DirectionalFollowupEvaluation, ...]
    average_positive_score: float | None
    average_negative_score: float | None
    positive_score_above_negative: bool | None
    positive_negative_margin: float | None
    top_results: tuple[RankedDrinkResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "profile_name": self.profile_name,
            "top_k_hit": self.top_k_hit,
            "top_result_positive_hit": self.top_result_positive_hit,
            "top_result_catalog_key": self.top_result_catalog_key,
            "category_style_match_rate": self.category_style_match_rate,
            "negative_violations": list(self.negative_violations),
            "reason_code_coverage": self.reason_code_coverage,
            "top_result_reason_hit": self.top_result_reason_hit,
            "top_result_reason_coverage": self.top_result_reason_coverage,
            "top_result_missing_reason_codes": list(
                self.top_result_missing_reason_codes,
            ),
            "diversity_followups": self.diversity_followups,
            "directional_followups": [
                followup.to_dict() for followup in self.directional_followups
            ],
            "average_positive_score": self.average_positive_score,
            "average_negative_score": self.average_negative_score,
            "positive_score_above_negative": self.positive_score_above_negative,
            "positive_negative_margin": self.positive_negative_margin,
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
            "fixture_results": [result.to_dict() for result in self.fixture_results],
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
    scoring_config_version: str = SCORING_V3,
    generated_at: datetime | None = None,
) -> DrinkEvaluationReport:
    scoring_config = _beverage_scoring_config(scoring_config_version)
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
    metrics = _aggregate_metrics(
        fixture_results,
        fixtures=fixtures,
        records=records,
        candidates=candidates,
        scoring_config=scoring_config,
        vector_schema_version_id=schema_id,
    )
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
        directional_followups=_directional_followup_tuple(
            payload.get("directional_followups"),
            fixture_id=fixture_id,
        ),
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
    top_result_catalog_key = top_results[0].catalog_key if top_results else None
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
        reason_code for result in top_results for reason_code in result.reason_codes
    }
    top_result_reasons = set(top_results[0].reason_codes) if top_results else set()
    top_result_matched_reasons = expected_reasons & top_result_reasons
    final_scores_by_key = {
        _catalog_key(candidate): score.final_score for candidate, score in scored
    }
    diversity_followups = _diversity_followups(ranked, profile)
    directional_followups = _evaluate_directional_followups(
        fixture=fixture,
        candidates=candidates,
        scoring_config=scoring_config,
        vector_schema_version_id=vector_schema_version_id,
        limit=limit,
    )
    average_positive_score = _average_scores(final_scores_by_key, positives)
    average_negative_score = _average_scores(final_scores_by_key, negatives)
    positive_negative_margin = _positive_negative_margin(
        average_positive_score,
        average_negative_score,
    )
    return FixtureEvaluationResult(
        fixture_id=fixture.fixture_id,
        profile_name=fixture.profile_name,
        top_k_hit=bool(positives & top_keys),
        top_result_positive_hit=(
            top_result_catalog_key is not None and top_result_catalog_key in positives
        ),
        top_result_catalog_key=top_result_catalog_key,
        category_style_match_rate=_ratio(
            len(category_or_style_matches),
            len(top_results),
        ),
        negative_violations=tuple(sorted(negatives & top_keys)),
        reason_code_coverage=_ratio(
            len(expected_reasons & actual_reasons),
            len(expected_reasons),
        ),
        top_result_reason_hit=bool(top_result_matched_reasons),
        top_result_reason_coverage=_ratio(
            len(top_result_matched_reasons),
            len(expected_reasons),
        ),
        top_result_missing_reason_codes=tuple(
            sorted(expected_reasons - top_result_reasons),
        ),
        diversity_followups=diversity_followups,
        directional_followups=directional_followups,
        average_positive_score=average_positive_score,
        average_negative_score=average_negative_score,
        positive_score_above_negative=(
            positive_negative_margin is not None and positive_negative_margin > 0
        ),
        positive_negative_margin=positive_negative_margin,
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
        mapper_version_id=uuid.uuid5(EVALUATION_NAMESPACE, SURVEY_MAPPER_V1_1),
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
    *,
    fixtures: tuple[DrinkEvaluationFixture, ...],
    records: tuple[CanonicalSeedRecord, ...],
    candidates: tuple[BeverageVectorCandidate, ...],
    scoring_config: ScoringConfig,
    vector_schema_version_id: uuid.UUID,
) -> dict[str, Any]:
    positive_negative_results = [
        result
        for result in fixture_results
        if result.positive_score_above_negative is not None
    ]
    positive_above_negative_count = sum(
        1
        for result in positive_negative_results
        if result.positive_score_above_negative
    )
    positive_score_failures = [
        _positive_score_failure_payload(result)
        for result in positive_negative_results
        if not result.positive_score_above_negative
    ]
    positive_negative_margins = [
        result.positive_negative_margin
        for result in positive_negative_results
        if result.positive_negative_margin is not None
    ]
    directional_followup_results = [
        followup
        for result in fixture_results
        for followup in result.directional_followups
    ]
    directional_followup_pass_count = sum(
        1
        for followup in directional_followup_results
        if followup.positive_score_above_negative
    )
    directional_followup_failures = [
        _directional_followup_failure_payload(result, followup)
        for result in fixture_results
        for followup in result.directional_followups
        if not followup.positive_score_above_negative
    ]
    directional_followup_direction_counts = Counter(
        followup.direction for followup in directional_followup_results
    )
    directional_followup_margins = [
        followup.positive_negative_margin
        for followup in directional_followup_results
        if followup.positive_negative_margin is not None
    ]
    top_result_reason_hit_count = sum(
        1 for result in fixture_results if result.top_result_reason_hit
    )
    top_result_positive_hit_count = sum(
        1 for result in fixture_results if result.top_result_positive_hit
    )
    different_changed_count = sum(
        1
        for result in fixture_results
        if _followup_bool(result, BEVERAGE_DIVERSITY_DIFFERENT, "changed_candidate")
    )
    different_style_or_category_changed_count = sum(
        1
        for result in fixture_results
        if _followup_bool(
            result,
            BEVERAGE_DIVERSITY_DIFFERENT,
            "changed_style_or_category",
        )
    )
    adjacent_changed_count = sum(
        1
        for result in fixture_results
        if _followup_bool(result, BEVERAGE_DIVERSITY_ADJACENT, "changed_candidate")
    )
    active_catalog_categories = sorted(
        {record.beverage.category for record in records if record.beverage.active},
    )
    fixture_category_counts = Counter(
        category
        for fixture in fixtures
        for category in fixture.expected_categories
    )
    fixture_expected_categories = sorted(fixture_category_counts)
    active_category_set = set(active_catalog_categories)
    fixture_category_set = set(fixture_expected_categories)
    covered_categories = sorted(active_category_set & fixture_category_set)
    missing_fixture_categories = sorted(active_category_set - fixture_category_set)
    unexpected_fixture_categories = sorted(fixture_category_set - active_category_set)
    fixture_counts_for_active_categories = [
        fixture_category_counts.get(category, 0)
        for category in active_catalog_categories
    ]
    experience_level_counts = Counter(
        level
        for fixture in fixtures
        if isinstance((level := fixture.survey_answers.get("experience_level")), str)
        and level
    )
    deployed_experience_levels = sorted(DEPLOYED_SURVEY_LEVELS)
    covered_experience_levels = sorted(
        set(deployed_experience_levels) & set(experience_level_counts),
    )
    budget_range_counts = Counter(
        budget
        for fixture in fixtures
        if isinstance((budget := _fixture_budget_range(fixture)), str)
        and budget
    )
    deployed_budget_ranges = sorted(
        {
            budget
            for raw_budget in DEPLOYED_SURVEY_BUDGET_RANGES
            if (budget := canonicalize_survey_budget_range(raw_budget)) is not None
        },
    )
    covered_deployed_budget_ranges = sorted(
        set(deployed_budget_ranges) & set(budget_range_counts),
    )
    experience_level_counts_for_deployed = [
        experience_level_counts.get(level, 0) for level in deployed_experience_levels
    ]
    budget_counts_for_deployed = [
        budget_range_counts.get(budget, 0) for budget in deployed_budget_ranges
    ]
    budget_sensitivity_metrics = _budget_sensitivity_metrics(
        fixtures=fixtures,
        candidates=candidates,
        scoring_config=scoring_config,
        vector_schema_version_id=vector_schema_version_id,
    )
    deployed_survey_fixture_metrics = _deployed_survey_fixture_metrics(fixtures)
    return {
        "fixture_count": len(fixture_results),
        "top_k_hit_rate": _ratio(
            sum(1 for result in fixture_results if result.top_k_hit),
            len(fixture_results),
        ),
        "top_result_positive_hit_rate": _ratio(
            top_result_positive_hit_count,
            len(fixture_results),
        ),
        "fixtures_missing_top_result_positive": [
            result.fixture_id
            for result in fixture_results
            if not result.top_result_positive_hit
        ],
        "average_category_style_match_rate": _average(
            result.category_style_match_rate for result in fixture_results
        ),
        "negative_violation_count": sum(
            len(result.negative_violations) for result in fixture_results
        ),
        "average_reason_code_coverage": _average(
            result.reason_code_coverage for result in fixture_results
        ),
        "top_result_reason_hit_rate": _ratio(
            top_result_reason_hit_count,
            len(fixture_results),
        ),
        "average_top_result_reason_coverage": _average(
            result.top_result_reason_coverage for result in fixture_results
        ),
        "fixtures_missing_top_result_reason": [
            result.fixture_id
            for result in fixture_results
            if not result.top_result_reason_hit
        ],
        "different_followup_change_rate": _ratio(
            different_changed_count,
            len(fixture_results),
        ),
        "different_followup_style_or_category_change_rate": _ratio(
            different_style_or_category_changed_count,
            len(fixture_results),
        ),
        "different_followup_missing": [
            result.fixture_id
            for result in fixture_results
            if not _followup_value(
                result,
                BEVERAGE_DIVERSITY_DIFFERENT,
                "catalog_key",
            )
        ],
        "different_followup_same_style_or_category": [
            result.fixture_id
            for result in fixture_results
            if _followup_value(
                result,
                BEVERAGE_DIVERSITY_DIFFERENT,
                "catalog_key",
            )
            and not _followup_bool(
                result,
                BEVERAGE_DIVERSITY_DIFFERENT,
                "changed_style_or_category",
            )
        ],
        "adjacent_followup_change_rate": _ratio(
            adjacent_changed_count,
            len(fixture_results),
        ),
        "adjacent_followup_missing": [
            result.fixture_id
            for result in fixture_results
            if not _followup_value(
                result,
                BEVERAGE_DIVERSITY_ADJACENT,
                "catalog_key",
            )
        ],
        "adjacent_followup_same_candidate": [
            result.fixture_id
            for result in fixture_results
            if _followup_value(
                result,
                BEVERAGE_DIVERSITY_ADJACENT,
                "catalog_key",
            )
            and not _followup_bool(
                result,
                BEVERAGE_DIVERSITY_ADJACENT,
                "changed_candidate",
            )
        ],
        "fixtures_with_positive_score_above_negative": (positive_above_negative_count),
        "positive_score_above_negative_rate": _ratio(
            positive_above_negative_count,
            len(positive_negative_results),
        ),
        "positive_score_not_above_negative_failures": positive_score_failures,
        "minimum_positive_negative_margin": (
            round(min(positive_negative_margins), 6)
            if positive_negative_margins
            else None
        ),
        "average_positive_negative_margin": _average(positive_negative_margins),
        "directional_followup_count": len(directional_followup_results),
        "directional_followup_score_preference_rate": _ratio(
            directional_followup_pass_count,
            len(directional_followup_results),
        ),
        "directional_followup_score_preference_failures": (
            directional_followup_failures
        ),
        "directional_followup_direction_counts": dict(
            sorted(directional_followup_direction_counts.items()),
        ),
        "directional_followup_direction_count": len(
            directional_followup_direction_counts,
        ),
        "minimum_directional_followups_per_direction": (
            min(directional_followup_direction_counts.values())
            if directional_followup_direction_counts
            else 0
        ),
        "minimum_directional_followup_margin": (
            round(min(directional_followup_margins), 6)
            if directional_followup_margins
            else None
        ),
        "average_directional_followup_margin": _average(
            directional_followup_margins,
        ),
        "active_catalog_categories": active_catalog_categories,
        "fixture_expected_categories": fixture_expected_categories,
        "fixture_category_counts": dict(sorted(fixture_category_counts.items())),
        "covered_active_categories": covered_categories,
        "missing_fixture_categories": missing_fixture_categories,
        "unexpected_fixture_categories": unexpected_fixture_categories,
        "active_category_fixture_coverage": _ratio(
            len(covered_categories),
            len(active_catalog_categories),
        ),
        "minimum_fixtures_per_active_category": (
            min(fixture_counts_for_active_categories)
            if fixture_counts_for_active_categories
            else 0
        ),
        "deployed_experience_levels": deployed_experience_levels,
        "fixture_experience_level_counts": dict(
            sorted(experience_level_counts.items()),
        ),
        "missing_experience_levels": sorted(
            set(deployed_experience_levels) - set(experience_level_counts),
        ),
        "experience_level_fixture_coverage": _ratio(
            len(covered_experience_levels),
            len(deployed_experience_levels),
        ),
        "minimum_fixtures_per_experience_level": (
            min(experience_level_counts_for_deployed)
            if experience_level_counts_for_deployed
            else 0
        ),
        "deployed_budget_ranges": deployed_budget_ranges,
        "fixture_budget_range_counts": dict(sorted(budget_range_counts.items())),
        "missing_deployed_budget_ranges": sorted(
            set(deployed_budget_ranges) - set(budget_range_counts),
        ),
        "deployed_budget_range_fixture_coverage": _ratio(
            len(covered_deployed_budget_ranges),
            len(deployed_budget_ranges),
        ),
        "minimum_fixtures_per_deployed_budget_range": (
            min(budget_counts_for_deployed) if budget_counts_for_deployed else 0
        ),
        **deployed_survey_fixture_metrics,
        **budget_sensitivity_metrics,
    }


def _deployed_survey_fixture_metrics(
    fixtures: tuple[DrinkEvaluationFixture, ...],
) -> dict[str, Any]:
    deployed_categories = tuple(DEPLOYED_SURVEY_CATEGORIES)
    deployed_category_set = set(deployed_categories)
    deployed_category_trait_tokens = tuple(
        f"{category}:{trait}"
        for category, traits in sorted(DEPLOYED_SURVEY_CATEGORY_TRAITS.items())
        for trait in traits
    )
    deployed_category_trait_set = set(deployed_category_trait_tokens)
    deployed_flavor_keywords = tuple(DEPLOYED_SURVEY_FLAVOR_KEYWORDS)
    deployed_flavor_keyword_set = set(deployed_flavor_keywords)

    fixture_categories: set[str] = set()
    fixture_category_trait_tokens: set[str] = set()
    fixture_flavor_keywords: set[str] = set()
    for fixture in fixtures:
        answers = fixture.survey_answers
        for category in _string_tuple(answers.get("categories")):
            if category in deployed_category_set:
                fixture_categories.add(category)
        category_traits = answers.get("category_traits")
        if isinstance(category_traits, dict):
            for raw_category, raw_traits in category_traits.items():
                if not isinstance(raw_category, str):
                    continue
                deployed_traits = DEPLOYED_SURVEY_CATEGORY_TRAITS.get(raw_category)
                if deployed_traits is None:
                    continue
                deployed_trait_set = set(deployed_traits)
                for trait in _string_tuple(raw_traits):
                    if trait in deployed_trait_set:
                        fixture_category_trait_tokens.add(f"{raw_category}:{trait}")
        for keyword in _string_tuple(answers.get("global_keywords")):
            if keyword in deployed_flavor_keyword_set:
                fixture_flavor_keywords.add(keyword)

    return {
        "deployed_survey_categories": list(deployed_categories),
        "fixture_deployed_survey_categories": sorted(fixture_categories),
        "missing_deployed_survey_categories": sorted(
            deployed_category_set - fixture_categories,
        ),
        "deployed_survey_category_fixture_coverage": _ratio(
            len(fixture_categories),
            len(deployed_categories),
        ),
        "deployed_survey_category_trait_tokens": list(deployed_category_trait_tokens),
        "fixture_deployed_survey_category_trait_tokens": sorted(
            fixture_category_trait_tokens,
        ),
        "missing_deployed_survey_category_trait_tokens": sorted(
            deployed_category_trait_set - fixture_category_trait_tokens,
        ),
        "deployed_survey_category_trait_fixture_coverage": _ratio(
            len(fixture_category_trait_tokens),
            len(deployed_category_trait_tokens),
        ),
        "deployed_survey_flavor_keywords": list(deployed_flavor_keywords),
        "fixture_deployed_survey_flavor_keywords": sorted(fixture_flavor_keywords),
        "missing_deployed_survey_flavor_keywords": sorted(
            deployed_flavor_keyword_set - fixture_flavor_keywords,
        ),
        "deployed_survey_flavor_keyword_fixture_coverage": _ratio(
            len(fixture_flavor_keywords),
            len(deployed_flavor_keywords),
        ),
    }


def _evaluate_directional_followups(
    *,
    fixture: DrinkEvaluationFixture,
    candidates: tuple[BeverageVectorCandidate, ...],
    scoring_config: ScoringConfig,
    vector_schema_version_id: uuid.UUID,
    limit: int,
) -> tuple[DirectionalFollowupEvaluation, ...]:
    return tuple(
        _evaluate_directional_followup(
            fixture=fixture,
            followup=followup,
            candidates=candidates,
            scoring_config=scoring_config,
            vector_schema_version_id=vector_schema_version_id,
            limit=limit,
        )
        for followup in fixture.directional_followups
    )


def _evaluate_directional_followup(
    *,
    fixture: DrinkEvaluationFixture,
    followup: DirectionalFollowupFixture,
    candidates: tuple[BeverageVectorCandidate, ...],
    scoring_config: ScoringConfig,
    vector_schema_version_id: uuid.UUID,
    limit: int,
) -> DirectionalFollowupEvaluation:
    profile = _profile_from_fixture(
        _fixture_with_directional_overrides(fixture, followup),
        vector_schema_version_id,
    )
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
    final_scores_by_key = {
        _catalog_key(candidate): score.final_score for candidate, score in scored
    }
    positives = set(followup.positive_catalog_keys)
    negatives = set(followup.negative_catalog_keys)
    average_positive_score = _average_scores(final_scores_by_key, positives)
    average_negative_score = _average_scores(final_scores_by_key, negatives)
    positive_negative_margin = _positive_negative_margin(
        average_positive_score,
        average_negative_score,
    )
    return DirectionalFollowupEvaluation(
        direction=followup.direction,
        positive_catalog_keys=followup.positive_catalog_keys,
        negative_catalog_keys=followup.negative_catalog_keys,
        average_positive_score=average_positive_score,
        average_negative_score=average_negative_score,
        positive_score_above_negative=(
            positive_negative_margin is not None and positive_negative_margin > 0
        ),
        positive_negative_margin=positive_negative_margin,
        missing_positive_catalog_keys=tuple(
            sorted(positives - set(final_scores_by_key)),
        ),
        missing_negative_catalog_keys=tuple(
            sorted(negatives - set(final_scores_by_key)),
        ),
        top_results=top_results,
    )


def _fixture_with_directional_overrides(
    fixture: DrinkEvaluationFixture,
    followup: DirectionalFollowupFixture,
) -> DrinkEvaluationFixture:
    survey_answers = dict(fixture.survey_answers)
    for key, value in followup.survey_answer_overrides.items():
        survey_answers[key] = value
    return replace(
        fixture,
        fixture_id=f"{fixture.fixture_id}:{followup.direction}",
        survey_answers=survey_answers,
        directional_followups=(),
    )


def _diversity_followups(
    ranked: list[tuple[BeverageVectorCandidate, Any]],
    profile: TasteProfileRevision,
) -> dict[str, Any]:
    if not ranked:
        return {
            "standard": {},
            BEVERAGE_DIVERSITY_DIFFERENT: _empty_followup(),
            BEVERAGE_DIVERSITY_ADJACENT: _empty_followup(),
        }

    standard_candidate, _score = ranked[0]
    excluded_ids = {standard_candidate.beverage.id}
    exclusion_context = _beverage_exclusion_context(ranked, excluded_ids)
    eligible_ranked = [
        (candidate, score)
        for candidate, score in ranked
        if candidate.beverage.id not in excluded_ids
    ]
    standard = _followup_candidate_payload(
        standard_candidate,
        standard_candidate=standard_candidate,
    )
    return {
        "standard": standard,
        BEVERAGE_DIVERSITY_DIFFERENT: _select_followup_payload(
            ranked=eligible_ranked,
            profile=profile,
            diversity_mode=BEVERAGE_DIVERSITY_DIFFERENT,
            excluded_styles=exclusion_context["styles"],
            excluded_categories=exclusion_context["categories"],
            standard_candidate=standard_candidate,
        ),
        BEVERAGE_DIVERSITY_ADJACENT: _select_followup_payload(
            ranked=eligible_ranked,
            profile=profile,
            diversity_mode=BEVERAGE_DIVERSITY_ADJACENT,
            excluded_styles=exclusion_context["styles"],
            excluded_categories=exclusion_context["categories"],
            standard_candidate=standard_candidate,
        ),
    }


def _select_followup_payload(
    *,
    ranked: list[tuple[BeverageVectorCandidate, Any]],
    profile: TasteProfileRevision,
    diversity_mode: str,
    excluded_styles: set[str],
    excluded_categories: set[str],
    standard_candidate: BeverageVectorCandidate,
) -> dict[str, Any]:
    selected = _select_beverage_recommendations(
        ranked=ranked,
        profile=profile,
        diversity_mode=diversity_mode,
        excluded_styles=excluded_styles,
        excluded_categories=excluded_categories,
        category_filter=None,
        limit=1,
    )
    if not selected:
        return _empty_followup()
    candidate, _score = selected[0]
    return _followup_candidate_payload(
        candidate,
        standard_candidate=standard_candidate,
    )


def _followup_candidate_payload(
    candidate: BeverageVectorCandidate,
    *,
    standard_candidate: BeverageVectorCandidate,
) -> dict[str, Any]:
    style = _style(candidate)
    category = candidate.beverage.category
    standard_style = _style(standard_candidate)
    standard_category = standard_candidate.beverage.category
    return {
        "catalog_key": _catalog_key(candidate),
        "category": category,
        "style": style,
        "changed_candidate": candidate.beverage.id != standard_candidate.beverage.id,
        "changed_style_or_category": (
            style != standard_style or category != standard_category
        ),
    }


def _empty_followup() -> dict[str, Any]:
    return {
        "catalog_key": None,
        "category": None,
        "style": None,
        "changed_candidate": False,
        "changed_style_or_category": False,
    }


def _followup_value(
    result: FixtureEvaluationResult,
    mode: str,
    key: str,
) -> Any:
    followup = result.diversity_followups.get(mode)
    if not isinstance(followup, dict):
        return None
    return followup.get(key)


def _followup_bool(
    result: FixtureEvaluationResult,
    mode: str,
    key: str,
) -> bool:
    return _followup_value(result, mode, key) is True


def _budget_sensitivity_metrics(
    *,
    fixtures: tuple[DrinkEvaluationFixture, ...],
    candidates: tuple[BeverageVectorCandidate, ...],
    scoring_config: ScoringConfig,
    vector_schema_version_id: uuid.UUID,
) -> dict[str, Any]:
    priced_candidates = [
        candidate
        for candidate in candidates
        if _candidate_price_mid_krw(candidate) is not None
    ]
    affordable_candidates = [
        candidate
        for candidate in priced_candidates
        if (
            price_mid := _candidate_price_mid_krw(candidate)
        ) is not None
        and price_mid <= BUDGET_SENSITIVITY_AFFORDABLE_CEILING_KRW
    ]
    premium_candidates = [
        candidate
        for candidate in priced_candidates
        if (
            price_mid := _candidate_price_mid_krw(candidate)
        ) is not None
        and price_mid >= BUDGET_SENSITIVITY_PREMIUM_FLOOR_KRW
    ]
    affordable_total, affordable_passes, affordable_failures = (
        _budget_preference_counts(
            fixtures=fixtures,
            candidates=tuple(affordable_candidates),
            scoring_config=scoring_config,
            vector_schema_version_id=vector_schema_version_id,
            expected_budget=BUDGET_SENSITIVITY_LOW_BUDGET,
            comparison_budget=BUDGET_SENSITIVITY_HIGH_BUDGET,
        )
    )
    premium_total, premium_passes, premium_failures = _budget_preference_counts(
        fixtures=fixtures,
        candidates=tuple(premium_candidates),
        scoring_config=scoring_config,
        vector_schema_version_id=vector_schema_version_id,
        expected_budget=BUDGET_SENSITIVITY_HIGH_BUDGET,
        comparison_budget=BUDGET_SENSITIVITY_LOW_BUDGET,
    )
    return {
        "budget_sensitivity_low_budget": BUDGET_SENSITIVITY_LOW_BUDGET,
        "budget_sensitivity_high_budget": BUDGET_SENSITIVITY_HIGH_BUDGET,
        "budget_affordable_candidate_count": len(affordable_candidates),
        "budget_premium_candidate_count": len(premium_candidates),
        "budget_affordable_score_preference_rate": _ratio(
            affordable_passes,
            affordable_total,
        ),
        "budget_premium_score_preference_rate": _ratio(
            premium_passes,
            premium_total,
        ),
        "budget_affordable_score_preference_failures": affordable_failures,
        "budget_premium_score_preference_failures": premium_failures,
    }


def _budget_preference_counts(
    *,
    fixtures: tuple[DrinkEvaluationFixture, ...],
    candidates: tuple[BeverageVectorCandidate, ...],
    scoring_config: ScoringConfig,
    vector_schema_version_id: uuid.UUID,
    expected_budget: str,
    comparison_budget: str,
) -> tuple[int, int, list[dict[str, Any]]]:
    total = 0
    passed = 0
    failures: list[dict[str, Any]] = []
    for fixture in fixtures:
        expected_profile = _profile_from_fixture(
            _fixture_with_budget(fixture, expected_budget),
            vector_schema_version_id,
        )
        comparison_profile = _profile_from_fixture(
            _fixture_with_budget(fixture, comparison_budget),
            vector_schema_version_id,
        )
        for candidate in candidates:
            total += 1
            expected_score = score_beverage_candidate(
                profile=expected_profile,
                candidate=candidate,
                scoring_config=scoring_config,
            ).final_score
            comparison_score = score_beverage_candidate(
                profile=comparison_profile,
                candidate=candidate,
                scoring_config=scoring_config,
            ).final_score
            if expected_score > comparison_score:
                passed += 1
                continue
            failures.append(
                {
                    "fixture_id": fixture.fixture_id,
                    "catalog_key": _catalog_key(candidate),
                    "price_mid_krw": _candidate_price_mid_krw(candidate),
                    "expected_budget": expected_budget,
                    "comparison_budget": comparison_budget,
                    "expected_score": expected_score,
                    "comparison_score": comparison_score,
                },
            )
    return total, passed, failures


def _fixture_with_budget(
    fixture: DrinkEvaluationFixture,
    budget_range: str,
) -> DrinkEvaluationFixture:
    survey_answers = dict(fixture.survey_answers)
    survey_answers["budget_range"] = budget_range
    return replace(fixture, survey_answers=survey_answers)


def _candidate_price_mid_krw(candidate: BeverageVectorCandidate) -> float | None:
    price_min = candidate.beverage.price_min_krw
    price_max = candidate.beverage.price_max_krw
    if price_min is None or price_max is None or price_min <= 0 or price_max <= 0:
        return None
    if price_min > price_max:
        return None
    return round((price_min + price_max) / 2, 2)


def _positive_negative_margin(
    average_positive_score: float | None,
    average_negative_score: float | None,
) -> float | None:
    if average_positive_score is None or average_negative_score is None:
        return None
    return round(average_positive_score - average_negative_score, 6)


def _positive_score_failure_payload(
    result: FixtureEvaluationResult,
) -> dict[str, Any]:
    return {
        "fixture_id": result.fixture_id,
        "profile_name": result.profile_name,
        "average_positive_score": result.average_positive_score,
        "average_negative_score": result.average_negative_score,
        "positive_negative_margin": result.positive_negative_margin,
    }


def _directional_followup_failure_payload(
    result: FixtureEvaluationResult,
    followup: DirectionalFollowupEvaluation,
) -> dict[str, Any]:
    return {
        "fixture_id": result.fixture_id,
        "profile_name": result.profile_name,
        "direction": followup.direction,
        "positive_catalog_keys": list(followup.positive_catalog_keys),
        "negative_catalog_keys": list(followup.negative_catalog_keys),
        "average_positive_score": followup.average_positive_score,
        "average_negative_score": followup.average_negative_score,
        "positive_negative_margin": followup.positive_negative_margin,
        "missing_positive_catalog_keys": list(followup.missing_positive_catalog_keys),
        "missing_negative_catalog_keys": list(followup.missing_negative_catalog_keys),
        "top_results": [result.to_dict() for result in followup.top_results],
    }


def _fixture_budget_range(fixture: DrinkEvaluationFixture) -> str | None:
    budget_range = fixture.survey_answers.get("budget_range")
    if not isinstance(budget_range, str) or not budget_range:
        return None
    return canonicalize_survey_budget_range(budget_range)


def _beverage_scoring_config(version: str) -> ScoringConfig:
    payloads_by_version = {
        SCORING_V1: scoring_v1_payloads,
        SCORING_V2: scoring_v2_payloads,
        SCORING_V3: scoring_v3_payloads,
    }
    payload_factory = payloads_by_version.get(version)
    if payload_factory is None:
        supported = ", ".join(sorted(payloads_by_version))
        raise EvaluationFixtureError(
            f"unsupported scoring_config_version={version}; supported={supported}",
        )
    payload = next(
        item for item in payload_factory() if item["target_type"] == "beverage"
    )
    return ScoringConfig(
        id=uuid.uuid5(EVALUATION_NAMESPACE, f"{version}:beverage"),
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


def _directional_followup_tuple(
    value: object,
    *,
    fixture_id: str,
) -> tuple[DirectionalFollowupFixture, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise EvaluationFixtureError(
            f"{fixture_id}: directional_followups must be a list",
        )
    return tuple(
        _directional_followup_from_payload(item, fixture_id=fixture_id)
        for item in value
    )


def _directional_followup_from_payload(
    payload: object,
    *,
    fixture_id: str,
) -> DirectionalFollowupFixture:
    if not isinstance(payload, dict):
        raise EvaluationFixtureError(
            f"{fixture_id}: directional_followup must be an object",
        )
    direction = _required_string(payload, "direction")
    survey_answer_overrides = payload.get("survey_answer_overrides")
    if not isinstance(survey_answer_overrides, dict) or not survey_answer_overrides:
        raise EvaluationFixtureError(
            f"{fixture_id}: answer_overrides is required for followup={direction}",
        )
    positives = _string_tuple(payload.get("positive_catalog_keys"))
    negatives = _string_tuple(payload.get("negative_catalog_keys"))
    if not positives:
        raise EvaluationFixtureError(
            f"{fixture_id}:{direction}: positive_catalog_keys is required",
        )
    if not negatives:
        raise EvaluationFixtureError(
            f"{fixture_id}:{direction}: negative_catalog_keys is required",
        )
    return DirectionalFollowupFixture(
        direction=direction,
        survey_answer_overrides=dict(survey_answer_overrides),
        positive_catalog_keys=positives,
        negative_catalog_keys=negatives,
    )


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
