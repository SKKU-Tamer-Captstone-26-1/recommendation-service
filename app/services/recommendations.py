from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.vector_schema import TASTE_V1_DIMENSIONS
from app.models.enums import (
    InteractionEventType,
    ProfileStatus,
    RecommendationTargetType,
)
from app.models.profile import TasteProfileRevision
from app.models.recommendation_event import (
    RecommendationExplanation,
    RecommendationInteraction,
    RecommendationRequest,
    RecommendationResult,
)
from app.models.versioning import ScoringConfig
from app.repositories.catalog import BeverageVectorCandidate, CatalogRepository
from app.repositories.profiles import ProfileRepository

DEFAULT_LIMIT = 20
MAX_LIMIT = 50


class RecommendationPreconditionError(ValueError):
    """Raised when the request needs unavailable production-grade evidence."""


@dataclass(frozen=True)
class ProfileStatusView:
    status: str
    profile_revision: int | None
    survey_response_id: str | None
    generated_at: datetime | None
    stale_reason: str | None = None


@dataclass(frozen=True)
class BeverageRecommendationItem:
    result_id: uuid.UUID
    rank: int
    target_id: str
    name_ko: str
    name_en: str | None
    category: str
    style: str | None
    similarity_score: float
    final_score: float
    score_breakdown: dict[str, float]
    reason_codes: list[str]
    explanation: str
    source_metadata: dict[str, Any]


@dataclass(frozen=True)
class BeverageRecommendationResponse:
    request_id: uuid.UUID | None
    profile_status: str
    profile_revision: int | None
    scoring_config_version: str | None
    results: tuple[BeverageRecommendationItem, ...]


@dataclass(frozen=True)
class InteractionRecordResult:
    interaction_id: uuid.UUID
    duplicate: bool


@dataclass(frozen=True)
class ScoreComputation:
    similarity: float
    final_score: float
    breakdown: dict[str, float]
    matched_dimensions: dict[str, float]
    reason_codes: list[str]
    explanation: str


class BeverageRecommendationService:
    """Deterministic PostgreSQL-first beverage recommendation pipeline."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._profiles = ProfileRepository(session)
        self._catalog = CatalogRepository(session)

    def get_profile_status(self, external_user_id: str) -> ProfileStatusView:
        state = self._profiles.get_profile_state(external_user_id)
        if state is None:
            return ProfileStatusView(
                status=ProfileStatus.MISSING.value,
                profile_revision=None,
                survey_response_id=None,
                generated_at=None,
            )
        revision = (
            self._profiles.get_profile_revision(state.active_profile_revision_id)
            if state.active_profile_revision_id
            else None
        )
        return ProfileStatusView(
            status=state.status,
            profile_revision=revision.profile_revision if revision else None,
            survey_response_id=revision.survey_response_id if revision else None,
            generated_at=revision.generated_at if revision else None,
        )

    def get_beverage_recommendations(
        self,
        *,
        external_user_id: str,
        category: str | None = None,
        limit: int | None = None,
        budget_mode: str = "soft",
    ) -> BeverageRecommendationResponse:
        if budget_mode == "strict":
            raise RecommendationPreconditionError(
                "strict budget filtering is unavailable until approved canonical "
                "price or map/place price snapshot semantics exist",
            )
        resolved_limit = min(max(limit or DEFAULT_LIMIT, 1), MAX_LIMIT)
        profile = self._profiles.get_active_profile_revision(external_user_id)
        if profile is None or profile.status != ProfileStatus.ACTIVE.value:
            status = self.get_profile_status(external_user_id)
            return BeverageRecommendationResponse(
                request_id=None,
                profile_status=status.status,
                profile_revision=status.profile_revision,
                scoring_config_version=None,
                results=(),
            )

        scoring_config = _active_beverage_scoring(self._session)
        candidates = self._catalog.list_active_beverage_vector_candidates(
            vector_schema_version_id=profile.vector_schema_version_id,
            category=category,
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
        )[:resolved_limit]

        request = RecommendationRequest(
            external_user_id=external_user_id,
            profile_revision_id=profile.id,
            target_type=RecommendationTargetType.BEVERAGE.value,
            filters_json={
                "category": category,
                "limit": resolved_limit,
                "budget_mode": budget_mode,
            },
            scoring_config_id=scoring_config.id,
            request_context_json={
                "pipeline": "postgres_beverage_v1",
                "qdrant_used": False,
            },
        )
        self._session.add(request)
        self._session.flush()

        response_items: list[BeverageRecommendationItem] = []
        for index, (candidate, score) in enumerate(ranked, start=1):
            result = RecommendationResult(
                request_id=request.id,
                rank=index,
                target_type=RecommendationTargetType.BEVERAGE.value,
                target_id=str(candidate.beverage.id),
                similarity_score=score.similarity,
                final_score=score.final_score,
                score_breakdown_json=score.breakdown,
                qdrant_point_id=None,
            )
            self._session.add(result)
            self._session.flush()
            explanation = RecommendationExplanation(
                result_id=result.id,
                reason_codes=score.reason_codes,
                matched_dimensions_json=score.matched_dimensions,
                template_version="reason_template_v1",
                explanation_text=score.explanation,
                debug_json={
                    "catalog_key": _catalog_key(candidate),
                    "qdrant_used": False,
                },
            )
            self._session.add(explanation)
            response_items.append(
                BeverageRecommendationItem(
                    result_id=result.id,
                    rank=index,
                    target_id=str(candidate.beverage.id),
                    name_ko=candidate.beverage.name_ko,
                    name_en=candidate.beverage.name_en,
                    category=candidate.beverage.category,
                    style=_style(candidate),
                    similarity_score=score.similarity,
                    final_score=score.final_score,
                    score_breakdown=score.breakdown,
                    reason_codes=score.reason_codes,
                    explanation=score.explanation,
                    source_metadata={
                        "catalog_key": _catalog_key(candidate),
                        "source_version": candidate.beverage.metadata_json.get(
                            "source_version",
                        ),
                        "price_policy": candidate.beverage.metadata_json.get(
                            "price_policy",
                        ),
                    },
                ),
            )

        return BeverageRecommendationResponse(
            request_id=request.id,
            profile_status=ProfileStatus.ACTIVE.value,
            profile_revision=profile.profile_revision,
            scoring_config_version=scoring_config.version,
            results=tuple(response_items),
        )

    def record_interaction(
        self,
        *,
        request_id: uuid.UUID,
        result_id: uuid.UUID | None,
        event_type: str,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> InteractionRecordResult:
        if event_type not in {event.value for event in InteractionEventType}:
            raise ValueError(f"unsupported recommendation event type: {event_type}")
        if idempotency_key:
            existing = self._session.scalar(
                select(RecommendationInteraction).where(
                    RecommendationInteraction.idempotency_key == idempotency_key,
                ),
            )
            if existing is not None:
                return InteractionRecordResult(existing.id, duplicate=True)
        interaction = RecommendationInteraction(
            request_id=request_id,
            result_id=result_id,
            event_type=event_type,
            idempotency_key=idempotency_key,
            metadata_json=metadata or {},
        )
        self._session.add(interaction)
        self._session.flush()
        return InteractionRecordResult(interaction.id, duplicate=False)


def score_beverage_candidate(
    *,
    profile: TasteProfileRevision,
    candidate: BeverageVectorCandidate,
    scoring_config: ScoringConfig,
) -> ScoreComputation:
    weights = scoring_config.weights_json
    similarity = _cosine(profile.taste_vector, candidate.vector.vector)
    category_fit = _category_fit(profile, candidate)
    budget_fit = 0.5
    experience_fit = _experience_fit(profile, candidate)
    popularity_or_quality = _popularity_or_quality(candidate)
    diversity_adjustment = 0.5
    breakdown = {
        "taste_similarity_weighted": round(
            similarity * float(weights.get("taste_similarity_weighted", 0.65)),
            6,
        ),
        "budget_fit": round(budget_fit * float(weights.get("budget_fit", 0.10)), 6),
        "category_fit": round(
            category_fit * float(weights.get("category_fit", 0.10)),
            6,
        ),
        "experience_fit": round(
            experience_fit * float(weights.get("experience_fit", 0.05)),
            6,
        ),
        "popularity_or_quality": round(
            popularity_or_quality * float(weights.get("popularity_or_quality", 0.05)),
            6,
        ),
        "diversity_adjustment": round(
            diversity_adjustment * float(weights.get("diversity_adjustment", 0.05)),
            6,
        ),
    }
    final_score = round(sum(breakdown.values()), 6)
    matched_dimensions = _matched_dimensions(profile, candidate)
    reason_codes = _reason_codes(profile, candidate, matched_dimensions)
    return ScoreComputation(
        similarity=round(similarity, 6),
        final_score=final_score,
        breakdown=breakdown,
        matched_dimensions=matched_dimensions,
        reason_codes=reason_codes,
        explanation=_explanation(candidate, reason_codes),
    )


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have the same dimension count")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


def _category_fit(
    profile: TasteProfileRevision,
    candidate: BeverageVectorCandidate,
) -> float:
    if not profile.preferred_categories:
        return 0.5
    return 1.0 if candidate.beverage.category in profile.preferred_categories else 0.25


def _experience_fit(
    profile: TasteProfileRevision,
    candidate: BeverageVectorCandidate,
) -> float:
    beginner_score = candidate.beverage.metadata_json.get("beginner_friendly_score")
    if not isinstance(beginner_score, int | float):
        return 0.5
    if profile.experience_level == "beginner":
        return float(beginner_score)
    if profile.experience_level == "expert":
        return 1.0 - max(0.0, float(beginner_score) - 0.6)
    return 0.65


def _popularity_or_quality(candidate: BeverageVectorCandidate) -> float:
    popularity = candidate.beverage.metadata_json.get("popularity_hint")
    if popularity == "global_high":
        return 0.85
    if popularity in {"global_high_premium", "korea_high"}:
        return 0.75
    if isinstance(popularity, str) and "medium" in popularity:
        return 0.65
    return 0.5


def _matched_dimensions(
    profile: TasteProfileRevision,
    candidate: BeverageVectorCandidate,
) -> dict[str, float]:
    profile_by_name = profile.taste_vector_json
    candidate_by_name = candidate.vector.vector_json
    matches: list[tuple[str, float]] = []
    for dimension in TASTE_V1_DIMENSIONS:
        profile_value = float(profile_by_name.get(dimension.name, 0.0))
        candidate_value = float(candidate_by_name.get(dimension.name, 0.0))
        strength = min(profile_value, candidate_value)
        if strength >= 0.4:
            matches.append((dimension.name, round(strength, 4)))
    return dict(sorted(matches, key=lambda item: (-item[1], item[0]))[:4])


def _reason_codes(
    profile: TasteProfileRevision,
    candidate: BeverageVectorCandidate,
    matched_dimensions: dict[str, float],
) -> list[str]:
    hints = candidate.beverage.metadata_json.get("reason_code_hints") or []
    reason_codes = set(hint for hint in hints if isinstance(hint, str))
    if "smoky" in matched_dimensions:
        reason_codes.add("MATCHES_SMOKY_PROFILE")
    if {"sweet", "woody"} & set(matched_dimensions):
        reason_codes.add("MATCHES_VANILLA_CARAMEL")
    if candidate.beverage.category in profile.preferred_categories:
        reason_codes.add("CATEGORY_MATCH")
    beginner_match = (
        profile.experience_level == "beginner"
        and _experience_fit(profile, candidate) >= 0.7
    )
    if beginner_match:
        reason_codes.add("BEGINNER_FRIENDLY")
    return sorted(reason_codes)


def _explanation(
    candidate: BeverageVectorCandidate,
    reason_codes: list[str],
) -> str:
    if not reason_codes:
        return (
            f"{candidate.beverage.name_ko} matches the closest available taste "
            "profile among reviewed beverages."
        )
    reason_text = ", ".join(code.lower().replace("_", " ") for code in reason_codes[:3])
    return f"{candidate.beverage.name_ko} is recommended because: {reason_text}."


def _catalog_key(candidate: BeverageVectorCandidate) -> str:
    value = candidate.beverage.metadata_json.get("catalog_key")
    return value if isinstance(value, str) else str(candidate.beverage.id)


def _style(candidate: BeverageVectorCandidate) -> str | None:
    value = candidate.beverage.metadata_json.get("style")
    return value if isinstance(value, str) else None


def _active_beverage_scoring(session: Session) -> ScoringConfig:
    scoring = session.scalar(
        select(ScoringConfig).where(
            ScoringConfig.version == "scoring_v1",
            ScoringConfig.target_type == RecommendationTargetType.BEVERAGE.value,
            ScoringConfig.category == "all",
            ScoringConfig.status == "active",
        ),
    )
    if scoring is None:
        raise ValueError("active beverage scoring_v1 config is missing")
    return scoring
