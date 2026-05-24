from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.vector_schema import TASTE_V1_DIMENSIONS
from app.models.catalog import BeverageItem
from app.models.enums import (
    InteractionEventType,
    ProfileStatus,
    RecommendationTargetType,
    VenueAvailabilityStatus,
    VenueFreshnessStatus,
    VenueOptionType,
)
from app.models.profile import TasteProfileRevision
from app.models.recommendation_event import (
    RecommendationExplanation,
    RecommendationInteraction,
    RecommendationRequest,
    RecommendationResult,
)
from app.models.versioning import ScoringConfig
from app.repositories.catalog import (
    BeverageVectorCandidate,
    CatalogRepository,
    VenueSnapshotCandidate,
)
from app.repositories.profiles import ProfileRepository

DEFAULT_LIMIT = 20
MAX_LIMIT = 50
DEFAULT_RADIUS_M = 3000
MAX_RADIUS_M = 50000
FRESH_INVENTORY_DAYS = 3
STALE_INVENTORY_DAYS = 7
EXCLUDE_INVENTORY_DAYS = 30
EXCLUDE_PRICE_EXPIRED_DAYS = 30


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
class VenueRecommendationItem:
    result_id: uuid.UUID
    rank: int
    place_id: str
    name: str
    place_type: str
    address: str | None
    option_type: str
    distance_m: float
    price_krw: int | None
    availability_status: str
    freshness_status: str
    final_score: float
    score_breakdown: dict[str, float]
    reason_codes: list[str]
    explanation: str
    source_metadata: dict[str, Any]


@dataclass(frozen=True)
class VenueRecommendationResponse:
    request_id: uuid.UUID | None
    profile_status: str
    profile_revision: int | None
    scoring_config_version: str | None
    results: tuple[VenueRecommendationItem, ...]


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


@dataclass(frozen=True)
class VenueScoreComputation:
    distance_m: float
    price_krw: int | None
    availability_status: str
    freshness_status: str
    final_score: float
    breakdown: dict[str, float]
    reason_codes: list[str]
    explanation: str
    source_snapshot: dict[str, Any]


@dataclass
class RankedVenueCandidate:
    candidate: VenueSnapshotCandidate
    option_type: str
    score: VenueScoreComputation


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
            model_features = beverage_model_features(
                profile=profile,
                candidate=candidate,
                score=score,
                scoring_config=scoring_config,
            )
            result = RecommendationResult(
                request_id=request.id,
                rank=index,
                target_type=RecommendationTargetType.BEVERAGE.value,
                target_id=str(candidate.beverage.id),
                similarity_score=score.similarity,
                final_score=score.final_score,
                score_breakdown_json=score.breakdown,
                source_snapshot_json={
                    "candidate_source": "postgres_catalog",
                    "catalog_key": _catalog_key(candidate),
                    "vector_id": str(candidate.vector.id),
                    "source_hash": candidate.vector.source_hash,
                    "model_features": model_features,
                },
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
                    "candidate_source": "postgres_catalog",
                    "model_features": model_features,
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
                        "candidate_source": "postgres_catalog",
                        "model_features": model_features,
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

    def get_venue_recommendations(
        self,
        *,
        external_user_id: str,
        selected_beverage_id: str,
        lat: float,
        lng: float,
        radius_m: int | None = None,
        limit: int | None = None,
        budget_mode: str = "soft",
        now: datetime | None = None,
    ) -> VenueRecommendationResponse:
        if budget_mode not in {"soft", "strict"}:
            raise ValueError("budget_mode must be soft or strict")
        selected_id = _parse_uuid(selected_beverage_id, "selected_beverage_id")
        _validate_coordinates(lat, lng)
        if radius_m is not None and radius_m <= 0:
            raise ValueError("radius_m must be greater than zero")
        resolved_radius = min(radius_m or DEFAULT_RADIUS_M, MAX_RADIUS_M)
        resolved_limit = min(max(limit or 3, 1), MAX_LIMIT)
        resolved_now = now or datetime.now(UTC)

        profile = self._profiles.get_active_profile_revision(external_user_id)
        if profile is None or profile.status != ProfileStatus.ACTIVE.value:
            status = self.get_profile_status(external_user_id)
            return VenueRecommendationResponse(
                request_id=None,
                profile_status=status.status,
                profile_revision=status.profile_revision,
                scoring_config_version=None,
                results=(),
            )

        beverage = self._catalog.get_active_beverage_item(selected_id)
        if beverage is None:
            raise ValueError("selected_beverage_id must reference an active beverage")

        scoring_config = _active_venue_scoring(self._session)
        candidates = self._catalog.list_selected_beverage_venue_candidates(
            beverage_item_id=selected_id,
        )
        ranked = rank_venue_candidates(
            profile=profile,
            selected_beverage=beverage,
            candidates=candidates,
            scoring_config=scoring_config,
            lat=lat,
            lng=lng,
            radius_m=resolved_radius,
            limit=resolved_limit,
            budget_mode=budget_mode,
            now=resolved_now,
        )
        if budget_mode == "strict" and not ranked:
            raise RecommendationPreconditionError(
                "strict budget mode requires eligible venues with valid "
                "price snapshots",
            )

        request = RecommendationRequest(
            external_user_id=external_user_id,
            profile_revision_id=profile.id,
            target_type=RecommendationTargetType.VENUE.value,
            filters_json={
                "selected_beverage_id": str(selected_id),
                "lat": lat,
                "lng": lng,
                "radius_m": resolved_radius,
                "limit": resolved_limit,
                "budget_mode": budget_mode,
            },
            scoring_config_id=scoring_config.id,
            request_context_json={
                "pipeline": "postgres_selected_beverage_venue_v1",
                "qdrant_used": False,
                "distance_strategy": "straight_line_mvp",
            },
        )
        self._session.add(request)
        self._session.flush()

        response_items: list[VenueRecommendationItem] = []
        for index, ranked_candidate in enumerate(ranked, start=1):
            score = ranked_candidate.score
            venue = ranked_candidate.candidate.venue
            result = RecommendationResult(
                request_id=request.id,
                rank=index,
                target_type=RecommendationTargetType.VENUE.value,
                target_id=venue.place_id,
                similarity_score=None,
                final_score=score.final_score,
                score_breakdown_json=score.breakdown,
                source_snapshot_json=score.source_snapshot,
                qdrant_point_id=None,
            )
            self._session.add(result)
            self._session.flush()
            explanation = RecommendationExplanation(
                result_id=result.id,
                reason_codes=score.reason_codes,
                matched_dimensions_json={
                    "selected_beverage_id": str(selected_id),
                    "distance_m": score.distance_m,
                },
                template_version="venue_reason_template_v1",
                explanation_text=score.explanation,
                debug_json={
                    "option_type": ranked_candidate.option_type,
                    "distance_strategy": "straight_line_mvp",
                },
            )
            self._session.add(explanation)
            response_items.append(
                VenueRecommendationItem(
                    result_id=result.id,
                    rank=index,
                    place_id=venue.place_id,
                    name=venue.name,
                    place_type=venue.place_type,
                    address=venue.address,
                    option_type=ranked_candidate.option_type,
                    distance_m=score.distance_m,
                    price_krw=score.price_krw,
                    availability_status=score.availability_status,
                    freshness_status=score.freshness_status,
                    final_score=score.final_score,
                    score_breakdown=score.breakdown,
                    reason_codes=score.reason_codes,
                    explanation=score.explanation,
                    source_metadata=score.source_snapshot,
                ),
            )

        return VenueRecommendationResponse(
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


def beverage_model_features(
    *,
    profile: TasteProfileRevision,
    candidate: BeverageVectorCandidate,
    score: ScoreComputation,
    scoring_config: ScoringConfig,
) -> dict[str, Any]:
    """Return model-ready, deterministic features used to score a beverage."""

    return {
        "taste_similarity": score.similarity,
        "category_fit": round(_category_fit(profile, candidate), 6),
        "budget_fit": 0.5,
        "experience_fit": round(_experience_fit(profile, candidate), 6),
        "popularity_or_quality": round(_popularity_or_quality(candidate), 6),
        "diversity_adjustment": 0.5,
        "score_breakdown": score.breakdown,
        "final_score": score.final_score,
        "matched_dimensions": score.matched_dimensions,
        "reason_codes": score.reason_codes,
        "profile_revision": profile.profile_revision,
        "profile_revision_id": str(profile.id) if profile.id else None,
        "vector_schema_version_id": str(profile.vector_schema_version_id),
        "scoring_config_version": scoring_config.version,
        "candidate_catalog_key": _catalog_key(candidate),
        "candidate_category": candidate.beverage.category,
        "candidate_style": _style(candidate),
        "candidate_vector_id": (
            str(candidate.vector.id) if candidate.vector.id else None
        ),
    }


def rank_venue_candidates(
    *,
    profile: TasteProfileRevision,
    selected_beverage: BeverageItem,
    candidates: tuple[VenueSnapshotCandidate, ...],
    scoring_config: ScoringConfig,
    lat: float,
    lng: float,
    radius_m: int,
    limit: int,
    budget_mode: str,
    now: datetime,
) -> tuple[RankedVenueCandidate, ...]:
    scored: list[RankedVenueCandidate] = []
    for candidate in candidates:
        score = score_venue_candidate(
            profile=profile,
            selected_beverage=selected_beverage,
            candidate=candidate,
            scoring_config=scoring_config,
            lat=lat,
            lng=lng,
            radius_m=radius_m,
            budget_mode=budget_mode,
            now=now,
        )
        if score is not None:
            scored.append(
                RankedVenueCandidate(
                    candidate=candidate,
                    option_type=VenueOptionType.BALANCED_BEST.value,
                    score=score,
                ),
            )
    if not scored:
        return ()

    selected: dict[str, RankedVenueCandidate] = {}

    nearest = min(
        (
            item
            for item in scored
            if _availability_score(item.candidate) >= 0.4
        ),
        key=lambda item: (item.score.distance_m, -item.score.final_score),
        default=None,
    )
    if nearest:
        _select_option(selected, nearest, VenueOptionType.NEAREST_REASONABLE.value)

    best_price = min(
        (item for item in scored if item.score.price_krw is not None),
        key=lambda item: (
            item.score.price_krw or 0,
            item.score.distance_m,
            -item.score.final_score,
        ),
        default=None,
    )
    if best_price:
        _select_option(selected, best_price, VenueOptionType.BEST_PRICE.value)

    balanced = max(
        scored,
        key=lambda item: (item.score.final_score, -item.score.distance_m),
    )
    _select_option(selected, balanced, VenueOptionType.BALANCED_BEST.value)

    for item in sorted(
        scored,
        key=lambda item: (-item.score.final_score, item.score.distance_m),
    ):
        if len(selected) >= limit:
            break
        _select_option(selected, item, VenueOptionType.BALANCED_BEST.value)

    return tuple(list(selected.values())[:limit])


def score_venue_candidate(
    *,
    profile: TasteProfileRevision,
    selected_beverage: BeverageItem,
    candidate: VenueSnapshotCandidate,
    scoring_config: ScoringConfig,
    lat: float,
    lng: float,
    radius_m: int,
    budget_mode: str,
    now: datetime,
) -> VenueScoreComputation | None:
    if not _venue_is_rankable(candidate):
        return None
    coordinates = _venue_coordinates(candidate.venue.snapshot_json)
    if coordinates is None:
        return None
    distance_m = round(_haversine_m(lat, lng, coordinates[0], coordinates[1]), 2)
    if distance_m > radius_m:
        return None

    inventory_freshness, inventory_freshness_score = _inventory_freshness(
        candidate,
        now,
    )
    if inventory_freshness == VenueFreshnessStatus.EXPIRED.value:
        return None

    price_freshness, price_freshness_score = _price_freshness(candidate, now)
    if price_freshness == VenueFreshnessStatus.EXPIRED.value:
        return None
    if budget_mode == "strict" and (
        candidate.price is None
        or price_freshness != VenueFreshnessStatus.FRESH.value
    ):
        return None

    availability_status = _availability_status(candidate)
    if availability_status == VenueAvailabilityStatus.UNAVAILABLE.value:
        return None

    weights = scoring_config.weights_json
    distance_fit = max(0.0, 1.0 - (distance_m / radius_m))
    budget_fit = _budget_fit(profile.budget_range, candidate.price, budget_mode)
    availability_confidence = _availability_score(candidate)
    price_confidence = _price_confidence(candidate)
    freshness = min(inventory_freshness_score, price_freshness_score)
    selected_beverage_match = 1.0
    breakdown = {
        "selected_beverage_match": round(
            selected_beverage_match
            * float(weights.get("taste_similarity_weighted", 0.35)),
            6,
        ),
        "distance_fit": round(
            distance_fit * float(weights.get("distance_fit", 0.20)),
            6,
        ),
        "budget_fit": round(
            budget_fit * float(weights.get("budget_fit", 0.10)),
            6,
        ),
        "availability_confidence": round(
            availability_confidence
            * float(weights.get("availability_confidence", 0.15)),
            6,
        ),
        "price_confidence": round(
            price_confidence * float(weights.get("price_confidence", 0.10)),
            6,
        ),
        "freshness_adjustment": round(
            freshness * float(weights.get("freshness_adjustment", 0.10)),
            6,
        ),
    }
    final_score = round(sum(breakdown.values()), 6)
    freshness_status = (
        VenueFreshnessStatus.FRESH.value
        if inventory_freshness == VenueFreshnessStatus.FRESH.value
        and price_freshness == VenueFreshnessStatus.FRESH.value
        else VenueFreshnessStatus.STALE.value
    )
    reason_codes = _venue_reason_codes(
        selected_beverage=selected_beverage,
        candidate=candidate,
        distance_m=distance_m,
        radius_m=radius_m,
        budget_fit=budget_fit,
        availability_status=availability_status,
        freshness_status=freshness_status,
    )
    return VenueScoreComputation(
        distance_m=distance_m,
        price_krw=candidate.price.price_krw if candidate.price else None,
        availability_status=availability_status,
        freshness_status=freshness_status,
        final_score=final_score,
        breakdown=breakdown,
        reason_codes=reason_codes,
        explanation=_venue_explanation(candidate, reason_codes),
        source_snapshot=_source_snapshot_metadata(candidate, distance_m),
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


def _parse_uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid UUID") from exc


def _validate_coordinates(lat: float, lng: float) -> None:
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        raise ValueError("lat/lng must be valid WGS84 coordinates")


def _venue_is_rankable(candidate: VenueSnapshotCandidate) -> bool:
    if candidate.venue.status not in {"active"}:
        return False
    if candidate.venue.publication_status not in {"published", "active", "public"}:
        return False
    if candidate.menu is None and candidate.inventory is None:
        return False
    if candidate.menu is not None and candidate.menu.status not in {"active"}:
        return False
    return True


def _venue_coordinates(snapshot_json: dict[str, Any]) -> tuple[float, float] | None:
    lat = snapshot_json.get("lat")
    lng = snapshot_json.get("lng")
    if lat is None or lng is None:
        location = snapshot_json.get("location")
        if isinstance(location, dict):
            lat = location.get("lat")
            lng = location.get("lng")
    if not isinstance(lat, int | float) or not isinstance(lng, int | float):
        return None
    return float(lat), float(lng)


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _availability_status(candidate: VenueSnapshotCandidate) -> str:
    if candidate.inventory is None:
        return VenueAvailabilityStatus.UNKNOWN.value
    status = candidate.inventory.availability_status
    if status in {"available", "in_stock"}:
        return VenueAvailabilityStatus.AVAILABLE.value
    if status in {"likely_available", "limited"}:
        return VenueAvailabilityStatus.LIKELY_AVAILABLE.value
    if status in {"unknown"}:
        return VenueAvailabilityStatus.UNKNOWN.value
    return VenueAvailabilityStatus.UNAVAILABLE.value


def _availability_score(candidate: VenueSnapshotCandidate) -> float:
    status = _availability_status(candidate)
    if status == VenueAvailabilityStatus.UNAVAILABLE.value:
        return 0.0
    if candidate.inventory is None:
        return 0.5
    if candidate.inventory.confidence is None:
        return 0.6 if status == VenueAvailabilityStatus.AVAILABLE.value else 0.5
    return max(0.0, min(1.0, float(candidate.inventory.confidence)))


def _inventory_freshness(
    candidate: VenueSnapshotCandidate,
    now: datetime,
) -> tuple[str, float]:
    if candidate.inventory is None:
        return VenueFreshnessStatus.STALE.value, 0.5
    last_seen = _aware(candidate.inventory.last_seen_at) or _aware(
        candidate.inventory.synced_at,
    )
    if last_seen is None:
        return VenueFreshnessStatus.STALE.value, 0.5
    age = _aware(now) - last_seen
    if age >= timedelta(days=EXCLUDE_INVENTORY_DAYS):
        return VenueFreshnessStatus.EXPIRED.value, 0.0
    if age <= timedelta(days=FRESH_INVENTORY_DAYS):
        return VenueFreshnessStatus.FRESH.value, 1.0
    if age > timedelta(days=STALE_INVENTORY_DAYS):
        return VenueFreshnessStatus.STALE.value, 0.55
    return VenueFreshnessStatus.STALE.value, 0.75


def _price_freshness(
    candidate: VenueSnapshotCandidate,
    now: datetime,
) -> tuple[str, float]:
    if candidate.price is None or candidate.price.valid_until is None:
        return VenueFreshnessStatus.STALE.value, 0.4
    valid_until = _aware(candidate.price.valid_until)
    if valid_until >= _aware(now):
        return VenueFreshnessStatus.FRESH.value, 1.0
    if _aware(now) - valid_until > timedelta(days=EXCLUDE_PRICE_EXPIRED_DAYS):
        return VenueFreshnessStatus.EXPIRED.value, 0.0
    return VenueFreshnessStatus.STALE.value, 0.5


def _price_confidence(candidate: VenueSnapshotCandidate) -> float:
    if candidate.price is None:
        return 0.3
    if candidate.price.confidence is None:
        return 0.5
    return max(0.0, min(1.0, float(candidate.price.confidence)))


def _budget_fit(
    budget_range: str | None,
    price_snapshot,
    budget_mode: str,
) -> float:
    if price_snapshot is None:
        return 0.0 if budget_mode == "strict" else 0.5
    if not budget_range:
        return 0.5
    max_budget = _max_budget_krw(budget_range)
    if max_budget is None:
        return 0.5
    price = price_snapshot.price_krw
    if price <= max_budget:
        return 1.0
    return max(0.1, min(0.9, max_budget / price))


def _max_budget_krw(budget_range: str) -> int | None:
    if "_" not in budget_range:
        return None
    tail = budget_range.rsplit("_", 1)[-1]
    try:
        return int(tail)
    except ValueError:
        return None


def _venue_reason_codes(
    *,
    selected_beverage: BeverageItem,
    candidate: VenueSnapshotCandidate,
    distance_m: float,
    radius_m: int,
    budget_fit: float,
    availability_status: str,
    freshness_status: str,
) -> list[str]:
    reason_codes = {"SELECTED_BEVERAGE_AVAILABLE"}
    if distance_m <= radius_m * 0.5:
        reason_codes.add("NEARBY_VENUE")
    if candidate.price is not None and budget_fit >= 1.0:
        reason_codes.add("WITHIN_BUDGET")
    if availability_status in {
        VenueAvailabilityStatus.AVAILABLE.value,
        VenueAvailabilityStatus.LIKELY_AVAILABLE.value,
    }:
        reason_codes.add("LIKELY_AVAILABLE")
    if freshness_status == VenueFreshnessStatus.FRESH.value:
        reason_codes.add("FRESH_INVENTORY")
    if selected_beverage.category:
        reason_codes.add("SELECTED_BEVERAGE_MATCH")
    return sorted(reason_codes)


def _venue_explanation(
    candidate: VenueSnapshotCandidate,
    reason_codes: list[str],
) -> str:
    reason_text = ", ".join(code.lower().replace("_", " ") for code in reason_codes[:3])
    return f"{candidate.venue.name} is recommended because: {reason_text}."


def _source_snapshot_metadata(
    candidate: VenueSnapshotCandidate,
    distance_m: float,
) -> dict[str, Any]:
    inventory = candidate.inventory
    price = candidate.price
    menu = candidate.menu
    return {
        "place_name": candidate.venue.name,
        "place_id": candidate.venue.place_id,
        "place_revision": candidate.venue.place_revision,
        "menu_item_id": menu.menu_item_id if menu else None,
        "menu_revision": menu.menu_revision if menu else None,
        "inventory_revision": inventory.inventory_revision if inventory else None,
        "price_revision": price.price_revision if price else None,
        "snapshot_synced_at": _iso(candidate.venue.synced_at),
        "inventory_confidence": inventory.confidence if inventory else None,
        "price_confidence": price.confidence if price else None,
        "distance_m": distance_m,
        "distance_strategy": "straight_line_mvp",
    }


def _select_option(
    selected: dict[str, RankedVenueCandidate],
    item: RankedVenueCandidate,
    option_type: str,
) -> None:
    place_id = item.candidate.venue.place_id
    option_reason = _option_reason_code(option_type)
    if place_id in selected:
        existing = selected[place_id]
        combined_reason_codes = sorted({*existing.score.reason_codes, option_reason})
        selected[place_id] = RankedVenueCandidate(
            candidate=existing.candidate,
            option_type=existing.option_type,
            score=_copy_venue_score(existing.score, combined_reason_codes),
        )
        return
    selected[place_id] = RankedVenueCandidate(
        candidate=item.candidate,
        option_type=option_type,
        score=_copy_venue_score(
            item.score,
            sorted({*item.score.reason_codes, option_reason}),
        ),
    )


def _copy_venue_score(
    score: VenueScoreComputation,
    reason_codes: list[str],
) -> VenueScoreComputation:
    source_snapshot = dict(score.source_snapshot)
    return VenueScoreComputation(
        distance_m=score.distance_m,
        price_krw=score.price_krw,
        availability_status=score.availability_status,
        freshness_status=score.freshness_status,
        final_score=score.final_score,
        breakdown=score.breakdown,
        reason_codes=reason_codes,
        explanation=_venue_option_explanation(
            str(source_snapshot.get("place_name") or "Venue"),
            reason_codes,
        ),
        source_snapshot=source_snapshot,
    )


def _venue_option_explanation(name: str, reason_codes: list[str]) -> str:
    reason_text = ", ".join(code.lower().replace("_", " ") for code in reason_codes[:3])
    return f"{name} is recommended because: {reason_text}."


def _option_reason_code(option_type: str) -> str:
    return {
        VenueOptionType.NEAREST_REASONABLE.value: "NEAREST_REASONABLE",
        VenueOptionType.BEST_PRICE.value: "BEST_PRICE",
        VenueOptionType.BALANCED_BEST.value: "BALANCED_BEST",
    }[option_type]


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _iso(value: datetime | None) -> str | None:
    aware = _aware(value)
    return aware.isoformat() if aware else None


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


def _active_venue_scoring(session: Session) -> ScoringConfig:
    scoring = session.scalar(
        select(ScoringConfig).where(
            ScoringConfig.version == "scoring_v1",
            ScoringConfig.target_type == RecommendationTargetType.VENUE.value,
            ScoringConfig.category == "all",
            ScoringConfig.status == "active",
        ),
    )
    if scoring is None:
        raise ValueError("active venue scoring_v1 config is missing")
    return scoring
