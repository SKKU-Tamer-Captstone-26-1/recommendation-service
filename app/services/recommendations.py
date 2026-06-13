from __future__ import annotations

import logging
import math
import uuid
from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.foundation_versions import (
    CATEGORY_DIMENSION_WEIGHTS_V1,
    CATEGORY_WEIGHTED_SIMILARITY_V1,
)
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
from app.services.runtime_metrics import runtime_metrics

DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_EXCLUDE_IDS = 50
MAX_VENUE_PLACE_TYPE_FILTERS = 10
DEFAULT_RADIUS_M = 3000
MAX_RADIUS_M = 50000
FRESH_INVENTORY_DAYS = 3
STALE_INVENTORY_DAYS = 7
EXCLUDE_INVENTORY_DAYS = 30
EXCLUDE_PRICE_EXPIRED_DAYS = 30
INTERACTION_EVENT_TYPES = frozenset(event.value for event in InteractionEventType)
ALLOWED_INTERACTION_METADATA_KEYS = frozenset(
    {
        "client_platform",
        "app_version",
        "surface",
        "session_id_hash",
        "list_position",
        "visible_ms",
        "source",
    },
)
INTERACTION_METADATA_STRING_KEYS = frozenset(
    {
        "client_platform",
        "app_version",
        "surface",
        "session_id_hash",
        "source",
    },
)
INTERACTION_METADATA_INTEGER_KEYS = frozenset({"list_position", "visible_ms"})
PII_LIKE_INTERACTION_METADATA_TOKENS = frozenset(
    {
        "auth",
        "authorization",
        "birthday",
        "email",
        "external_user_id",
        "jwt",
        "name",
        "phone",
        "token",
        "user_id",
    },
)
MAX_INTERACTION_METADATA_STRING_LENGTH = 256
MAX_INTERACTION_METADATA_INTEGER = 86_400_000
BEVERAGE_DIVERSITY_STANDARD = "standard"
BEVERAGE_DIVERSITY_DIFFERENT = "different"
BEVERAGE_DIVERSITY_ADJACENT = "adjacent"
BEVERAGE_DIVERSITY_MODES = frozenset(
    {
        BEVERAGE_DIVERSITY_STANDARD,
        BEVERAGE_DIVERSITY_DIFFERENT,
        BEVERAGE_DIVERSITY_ADJACENT,
    },
)
BEVERAGE_FLAVOR_DIRECTION_SWEETER = "sweeter"
BEVERAGE_FLAVOR_DIRECTION_LESS_SWEET = "less_sweet"
BEVERAGE_FLAVOR_DIRECTION_SMOKIER = "smokier"
BEVERAGE_FLAVOR_DIRECTION_LESS_SMOKY = "less_smoky"
BEVERAGE_FLAVOR_DIRECTION_LIGHTER = "lighter"
BEVERAGE_FLAVOR_DIRECTION_RICHER = "richer"
BEVERAGE_FLAVOR_DIRECTION_MORE_HERBAL_BITTER = "more_herbal_bitter"
BEVERAGE_FLAVOR_DIRECTION_BRIGHTER_FRUITY = "brighter_fruity"
BEVERAGE_FLAVOR_DIRECTION_MODES = frozenset(
    {
        BEVERAGE_FLAVOR_DIRECTION_SWEETER,
        BEVERAGE_FLAVOR_DIRECTION_LESS_SWEET,
        BEVERAGE_FLAVOR_DIRECTION_SMOKIER,
        BEVERAGE_FLAVOR_DIRECTION_LESS_SMOKY,
        BEVERAGE_FLAVOR_DIRECTION_LIGHTER,
        BEVERAGE_FLAVOR_DIRECTION_RICHER,
        BEVERAGE_FLAVOR_DIRECTION_MORE_HERBAL_BITTER,
        BEVERAGE_FLAVOR_DIRECTION_BRIGHTER_FRUITY,
    },
)
BEVERAGE_FLAVOR_DIRECTION_POLICY_V1 = "beverage_flavor_direction_v1"
BEVERAGE_FLAVOR_DIRECTION_ADJUSTMENT_WEIGHT = 0.12
BEVERAGE_FLAVOR_DIRECTION_DIMENSION_WEIGHTS: dict[str, dict[str, float]] = {
    BEVERAGE_FLAVOR_DIRECTION_SWEETER: {
        "sweet": 1.0,
        "dried_fruit": 0.25,
        "body": 0.15,
    },
    BEVERAGE_FLAVOR_DIRECTION_LESS_SWEET: {
        "sweet": -1.0,
        "acidity": 0.25,
        "bitterness": 0.15,
    },
    BEVERAGE_FLAVOR_DIRECTION_SMOKIER: {
        "smoky": 1.0,
        "roasted": 0.35,
        "alcohol_intensity": 0.20,
    },
    BEVERAGE_FLAVOR_DIRECTION_LESS_SMOKY: {
        "smoky": -1.0,
        "roasted": -0.25,
        "floral": 0.20,
        "fruity": 0.20,
    },
    BEVERAGE_FLAVOR_DIRECTION_LIGHTER: {
        "body": -0.70,
        "alcohol_intensity": -0.50,
        "acidity": 0.35,
        "carbonation": 0.25,
    },
    BEVERAGE_FLAVOR_DIRECTION_RICHER: {
        "body": 0.85,
        "woody": 0.35,
        "dried_fruit": 0.35,
        "sweet": 0.20,
    },
    BEVERAGE_FLAVOR_DIRECTION_MORE_HERBAL_BITTER: {
        "herbal": 0.75,
        "bitterness": 0.65,
        "alcohol_intensity": 0.20,
    },
    BEVERAGE_FLAVOR_DIRECTION_BRIGHTER_FRUITY: {
        "fruity": 0.80,
        "acidity": 0.65,
        "floral": 0.20,
    },
}
DISTANCE_STRATEGY_STRAIGHT_LINE_MVP = "straight_line_mvp"
DISTANCE_STRATEGY_MAP_ROUTE_ESTIMATE_V1 = "map_route_estimate_v1"
DISTANCE_SOURCE_VENUE_SNAPSHOT_COORDINATES = "venue_snapshot_coordinates"
DISTANCE_SOURCE_MAP_SERVICE_ROUTE_API = "map_service_route_api"
STRAIGHT_LINE_DISTANCE_CONFIDENCE = 0.45
BEVERAGE_BUDGET_STRATEGY_CATALOG_PRICE_SOFT = "catalog_price_range_soft_v1"
BEVERAGE_SIMILARITY_STRATEGY_COSINE = "cosine_taste_v1"
BEVERAGE_PRICE_POLICY_VERIFIED_KRW = "verified_krw_observations_not_live_truth"
BEVERAGE_BUDGET_TRADEOFF_POLICY_V1 = "beverage_budget_tradeoff_v1"
NEUTRAL_BUDGET_FIT = 0.5
BEVERAGE_FEEDBACK_POLICY_RECENT_DISMISS = "recent_dismiss_v1"
VENUE_PLACE_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "bar": ("bar", "cocktail_bar", "pub", "whiskey_bar", "wine_bar"),
    "bottle_shop": ("bottle_shop",),
    "cocktail_bar": ("cocktail_bar",),
    "liquor_shop": ("liquor_shop",),
    "outdoor": ("outdoor_spot", "outdoor"),
    "outdoor_spot": ("outdoor_spot",),
    "pub": ("pub", "bar"),
    "restaurant": ("restaurant",),
    "shop": ("bottle_shop", "liquor_shop", "store"),
    "store": ("bottle_shop", "liquor_shop", "store"),
    "whiskey_bar": ("whiskey_bar",),
    "wine_bar": ("wine_bar",),
}
BEVERAGE_FEEDBACK_POSITIVE_EVENTS = frozenset(
    {
        InteractionEventType.CLICK.value,
        InteractionEventType.SAVE.value,
        InteractionEventType.DETAIL_VIEW.value,
    },
)
BeverageReasonText = dict[str, tuple[str, str]]
BEVERAGE_REASON_TEXT_KO: BeverageReasonText = {
    "CATEGORY_MATCH": (
        "선호 카테고리와 일치",
        "선택한 카테고리와 잘 맞습니다",
    ),
    "MATCHES_VANILLA_CARAMEL": (
        "바닐라/캐러멜 계열",
        "달콤한 바닐라와 캐러멜 느낌을 선호하는 취향에 맞습니다",
    ),
    "MATCHES_SMOKY_PROFILE": (
        "스모키한 개성",
        "스모키하거나 피트감 있는 향을 원하는 취향에 어울립니다",
    ),
    "MATCHES_FRUITY_BRIGHT_PROFILE": (
        "상큼하고 과실감 있는 방향",
        "과실감과 산뜻한 산미를 선호하는 취향에 가깝습니다",
    ),
    "MATCHES_HERBAL_BITTER_PROFILE": (
        "허브/쌉쌀한 뉘앙스",
        "허브, 민트, 쌉쌀한 계열을 좋아하는 취향과 연결됩니다",
    ),
    "MATCHES_RICH_OAK_PROFILE": (
        "오크와 묵직한 바디",
        "오크감과 묵직한 바디를 원하는 취향에 잘 맞습니다",
    ),
    "MATCHES_ROUNDED_BODY": (
        "둥글고 균형 잡힌 바디",
        "부드럽고 둥근 바디감을 기대할 수 있습니다",
    ),
    "MATCHES_ROASTED_PROFILE": (
        "로스티드/커피 계열",
        "커피, 코코아, 구운 곡물 같은 로스티드 계열과 맞습니다",
    ),
    "MATCHES_EARTHY_AGAVE_PROFILE": (
        "흙내음과 아가베 계열",
        "흙내음이나 아가베 특유의 개성을 원하는 취향에 어울립니다",
    ),
    "MATCHES_CLEAN_LIGHT_PROFILE": (
        "깔끔하고 가벼운 방향",
        "향이 과하게 무겁지 않은 깔끔한 술을 찾을 때 적합합니다",
    ),
    "BEGINNER_FRIENDLY": (
        "입문자 친화적",
        "처음 마시는 사람도 비교적 부담 없이 접근하기 좋습니다",
    ),
    "WITHIN_BUDGET": (
        "예산 적합",
        "검증된 카탈로그 가격대 기준으로 예산과 잘 맞습니다",
    ),
    "ADJACENT_DISCOVERY": (
        "취향 확장 후보",
        "기존 취향과 가까우면서도 새로운 방향으로 확장하기 좋습니다",
    ),
    "MATCHES_REQUESTED_FLAVOR_DIRECTION": (
        "요청한 맛 방향",
        "요청한 맛 방향과 비교적 잘 맞는 후보입니다",
    ),
}
BEVERAGE_REASON_PRIORITY = (
    "CATEGORY_MATCH",
    "MATCHES_VANILLA_CARAMEL",
    "MATCHES_SMOKY_PROFILE",
    "MATCHES_FRUITY_BRIGHT_PROFILE",
    "MATCHES_HERBAL_BITTER_PROFILE",
    "MATCHES_RICH_OAK_PROFILE",
    "MATCHES_ROUNDED_BODY",
    "MATCHES_ROASTED_PROFILE",
    "MATCHES_EARTHY_AGAVE_PROFILE",
    "MATCHES_CLEAN_LIGHT_PROFILE",
    "BEGINNER_FRIENDLY",
    "WITHIN_BUDGET",
    "MATCHES_REQUESTED_FLAVOR_DIRECTION",
    "ADJACENT_DISCOVERY",
)

logger = logging.getLogger(__name__)


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
class BeverageBudgetFeature:
    strategy: str
    fit: float
    confidence: float
    evidence: str
    budget_range: str | None
    budget_floor_krw: int | None
    budget_ceiling_krw: int | None
    price_min_krw: int | None
    price_max_krw: int | None
    price_mid_krw: float | None
    price_policy: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "fit": self.fit,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "budget_range": self.budget_range,
            "budget_floor_krw": self.budget_floor_krw,
            "budget_ceiling_krw": self.budget_ceiling_krw,
            "price_min_krw": self.price_min_krw,
            "price_max_krw": self.price_max_krw,
            "price_mid_krw": self.price_mid_krw,
            "price_policy": self.price_policy,
        }


@dataclass(frozen=True)
class BeverageSimilarityFeature:
    strategy: str
    similarity: float
    category: str
    dimension_weights: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "similarity": self.similarity,
            "category": self.category,
            "dimension_weights": self.dimension_weights,
        }


@dataclass(frozen=True)
class BeverageFlavorDirectionFeature:
    policy: str
    direction: str
    fit: float
    adjustment: float
    dimension_weights: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "direction": self.direction,
            "fit": self.fit,
            "adjustment": self.adjustment,
            "dimension_weights": self.dimension_weights,
        }


@dataclass(frozen=True)
class BeverageFeedbackContext:
    policy: str
    suppressed_ids: set[uuid.UUID]
    positive_ids: set[uuid.UUID]


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


@dataclass(frozen=True)
class VenueDistanceFeature:
    distance_m: float
    strategy: str
    source: str
    confidence: float
    is_route_distance: bool
    straight_line_distance_m: float | None = None
    route_distance_m: float | None = None
    route_duration_seconds: int | None = None
    route_complexity: str | None = None
    fallback_used: bool = False


@dataclass(frozen=True)
class MapRouteDistanceEstimate:
    route_distance_m: float
    route_duration_seconds: int | None = None
    route_complexity: str | None = None
    confidence: float = 0.8
    strategy: str = DISTANCE_STRATEGY_MAP_ROUTE_ESTIMATE_V1
    source: str = DISTANCE_SOURCE_MAP_SERVICE_ROUTE_API


class VenueDistanceProvider(Protocol):
    def distance_for(
        self,
        candidate: VenueSnapshotCandidate,
        *,
        origin_lat: float,
        origin_lng: float,
        now: datetime,
    ) -> VenueDistanceFeature | None: ...


class MapRouteDistanceClient(Protocol):
    def route_distance(
        self,
        *,
        place_id: str,
        origin_lat: float,
        origin_lng: float,
        destination_lat: float,
        destination_lng: float,
        requested_at: datetime,
    ) -> MapRouteDistanceEstimate | None: ...


class StraightLineVenueDistanceProvider:
    def distance_for(
        self,
        candidate: VenueSnapshotCandidate,
        *,
        origin_lat: float,
        origin_lng: float,
        now: datetime,
    ) -> VenueDistanceFeature | None:
        coordinates = _venue_coordinates(candidate.venue.snapshot_json)
        if coordinates is None:
            return None
        distance_m = round(
            _haversine_m(origin_lat, origin_lng, coordinates[0], coordinates[1]),
            2,
        )
        return VenueDistanceFeature(
            distance_m=distance_m,
            strategy=DISTANCE_STRATEGY_STRAIGHT_LINE_MVP,
            source=DISTANCE_SOURCE_VENUE_SNAPSHOT_COORDINATES,
            confidence=STRAIGHT_LINE_DISTANCE_CONFIDENCE,
            is_route_distance=False,
            straight_line_distance_m=distance_m,
        )


class MapRouteDistanceProvider:
    def __init__(self, client: MapRouteDistanceClient) -> None:
        self._client = client

    def distance_for(
        self,
        candidate: VenueSnapshotCandidate,
        *,
        origin_lat: float,
        origin_lng: float,
        now: datetime,
    ) -> VenueDistanceFeature | None:
        coordinates = _venue_coordinates(candidate.venue.snapshot_json)
        if coordinates is None:
            return None
        destination_lat, destination_lng = coordinates
        estimate = self._client.route_distance(
            place_id=candidate.venue.place_id,
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            destination_lat=destination_lat,
            destination_lng=destination_lng,
            requested_at=now,
        )
        if estimate is None:
            return None
        straight_line_distance_m = round(
            _haversine_m(origin_lat, origin_lng, destination_lat, destination_lng),
            2,
        )
        if not _is_finite_number(estimate.route_distance_m):
            return None
        route_distance_m = round(float(estimate.route_distance_m), 2)
        return VenueDistanceFeature(
            distance_m=route_distance_m,
            strategy=estimate.strategy,
            source=estimate.source,
            confidence=estimate.confidence,
            is_route_distance=True,
            straight_line_distance_m=straight_line_distance_m,
            route_distance_m=route_distance_m,
            route_duration_seconds=estimate.route_duration_seconds,
            route_complexity=estimate.route_complexity,
        )


class FallbackVenueDistanceProvider:
    def __init__(
        self,
        primary: VenueDistanceProvider,
        fallback: VenueDistanceProvider | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback or StraightLineVenueDistanceProvider()

    def distance_for(
        self,
        candidate: VenueSnapshotCandidate,
        *,
        origin_lat: float,
        origin_lng: float,
        now: datetime,
    ) -> VenueDistanceFeature | None:
        primary_distance = self._primary.distance_for(
            candidate,
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            now=now,
        )
        if primary_distance is not None:
            if _is_valid_venue_distance_feature(primary_distance):
                return primary_distance
            logger.warning(
                "invalid primary venue distance feature; using fallback",
                extra={
                    "structured": {
                        "event": "recommendation.invalid_primary_distance_feature",
                        "distance_strategy": primary_distance.strategy,
                        "distance_source": primary_distance.source,
                    },
                },
            )
        fallback_distance = self._fallback.distance_for(
            candidate,
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            now=now,
        )
        if fallback_distance is None:
            return None
        return replace(fallback_distance, fallback_used=True)


DEFAULT_VENUE_DISTANCE_PROVIDER = StraightLineVenueDistanceProvider()


def create_venue_distance_provider(
    settings: Any,
    *,
    route_client: MapRouteDistanceClient | None = None,
) -> VenueDistanceProvider:
    if not bool(getattr(settings, "map_route_distance_enabled", False)):
        return StraightLineVenueDistanceProvider()
    if route_client is None:
        logger.warning(
            "map route distance is enabled but no route client is configured; "
            "using straight-line distance",
            extra={
                "structured": {
                    "event": "recommendation.map_route_distance_client_missing",
                },
            },
        )
        return StraightLineVenueDistanceProvider()

    route_provider = MapRouteDistanceProvider(route_client)
    if bool(getattr(settings, "map_route_distance_fallback_enabled", True)):
        return FallbackVenueDistanceProvider(
            primary=route_provider,
            fallback=StraightLineVenueDistanceProvider(),
        )
    return route_provider


def _is_valid_venue_distance_feature(feature: VenueDistanceFeature) -> bool:
    if not _is_finite_non_negative_number(feature.distance_m):
        return False
    if not isinstance(feature.strategy, str) or not feature.strategy.strip():
        return False
    if not isinstance(feature.source, str) or not feature.source.strip():
        return False
    if not _is_finite_number(feature.confidence) or not 0 <= feature.confidence <= 1:
        return False
    if not isinstance(feature.is_route_distance, bool):
        return False
    if not isinstance(feature.fallback_used, bool):
        return False

    straight_line_distance_m = feature.straight_line_distance_m
    route_distance_m = feature.route_distance_m
    route_duration_seconds = feature.route_duration_seconds

    if feature.is_route_distance:
        if not _is_finite_non_negative_number(route_distance_m):
            return False
        if not math.isclose(feature.distance_m, float(route_distance_m), abs_tol=0.01):
            return False
        if straight_line_distance_m is not None and not _is_finite_non_negative_number(
            straight_line_distance_m,
        ):
            return False
        if route_duration_seconds is not None and (
            not isinstance(route_duration_seconds, int)
            or route_duration_seconds < 0
        ):
            return False
        return True

    if not _is_finite_non_negative_number(straight_line_distance_m):
        return False
    if not math.isclose(
        feature.distance_m,
        float(straight_line_distance_m),
        abs_tol=0.01,
    ):
        return False
    if route_distance_m is not None or route_duration_seconds is not None:
        return False
    return True


def _is_finite_non_negative_number(value: object) -> bool:
    return _is_finite_number(value) and float(value) >= 0


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    return math.isfinite(float(value))


class BeverageRecommendationService:
    """Deterministic PostgreSQL-first beverage recommendation pipeline."""

    def __init__(
        self,
        session: Session,
        *,
        active_scoring_config: str | None = None,
        venue_distance_provider: VenueDistanceProvider | None = None,
    ) -> None:
        self._session = session
        self._profiles = ProfileRepository(session)
        self._catalog = CatalogRepository(session)
        self._active_scoring_config = (
            active_scoring_config or get_settings().active_scoring_config
        )
        self._venue_distance_provider = (
            venue_distance_provider or DEFAULT_VENUE_DISTANCE_PROVIDER
        )

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
        exclude_beverage_ids: list[str] | None = None,
        exclude_result_ids: list[str] | None = None,
        diversity_mode: str = BEVERAGE_DIVERSITY_STANDARD,
        flavor_direction: str | None = None,
    ) -> BeverageRecommendationResponse:
        started_at = perf_counter()
        if budget_mode == "strict":
            raise RecommendationPreconditionError(
                "strict budget filtering is unavailable until approved canonical "
                "price or map/place price snapshot semantics exist",
            )
        resolved_limit = min(max(limit or DEFAULT_LIMIT, 1), MAX_LIMIT)
        resolved_diversity_mode = _normalize_beverage_diversity_mode(diversity_mode)
        resolved_flavor_direction = _normalize_beverage_flavor_direction(
            flavor_direction,
        )
        direct_excluded_ids = _parse_uuid_values(
            exclude_beverage_ids,
            "exclude_beverage_ids",
        )
        parsed_excluded_result_ids = _parse_uuid_values(
            exclude_result_ids,
            "exclude_result_ids",
        )
        result_excluded_ids = _beverage_ids_from_result_ids(
            self._session,
            parsed_excluded_result_ids,
        )
        feedback_context = _beverage_feedback_context(
            self._session,
            external_user_id,
        )
        excluded_beverage_ids = (
            direct_excluded_ids
            | result_excluded_ids
            | feedback_context.suppressed_ids
        )
        profile = self._profiles.get_active_profile_revision(external_user_id)
        if profile is None or profile.status != ProfileStatus.ACTIVE.value:
            status = self.get_profile_status(external_user_id)
            _log_recommendation_skipped(
                target_type=RecommendationTargetType.BEVERAGE.value,
                profile_status=status.status,
                profile_revision=status.profile_revision,
                error_type="profile_not_active",
                latency_ms=_elapsed_ms(started_at),
            )
            return BeverageRecommendationResponse(
                request_id=None,
                profile_status=status.status,
                profile_revision=status.profile_revision,
                scoring_config_version=None,
                results=(),
            )

        scoring_config = _active_beverage_scoring(
            self._session,
            self._active_scoring_config,
        )
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
                    flavor_direction=resolved_flavor_direction,
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
        exclusion_context = _beverage_exclusion_context(ranked, excluded_beverage_ids)
        eligible_ranked = [
            (candidate, score)
            for candidate, score in ranked
            if candidate.beverage.id not in excluded_beverage_ids
        ]
        selected_ranked = _select_beverage_recommendations(
            ranked=eligible_ranked,
            profile=profile,
            diversity_mode=resolved_diversity_mode,
            excluded_styles=exclusion_context["styles"],
            excluded_categories=exclusion_context["categories"],
            category_filter=category,
            limit=resolved_limit,
        )

        request = RecommendationRequest(
            external_user_id=external_user_id,
            profile_revision_id=profile.id,
            target_type=RecommendationTargetType.BEVERAGE.value,
            filters_json={
                "category": category,
                "limit": resolved_limit,
                "budget_mode": budget_mode,
                "exclude_beverage_ids": _sorted_uuid_strings(direct_excluded_ids),
                "exclude_result_ids": _sorted_uuid_strings(parsed_excluded_result_ids),
                "diversity_mode": resolved_diversity_mode,
                "flavor_direction": resolved_flavor_direction,
                "feedback_suppression": {
                    "policy": feedback_context.policy,
                    "suppressed_beverage_ids": _sorted_uuid_strings(
                        feedback_context.suppressed_ids,
                    ),
                    "positive_beverage_ids": _sorted_uuid_strings(
                        feedback_context.positive_ids,
                    ),
                },
            },
            scoring_config_id=scoring_config.id,
            request_context_json={
                "pipeline": "postgres_beverage_v1",
                "qdrant_used": False,
                "excluded_beverage_count": len(excluded_beverage_ids),
                "excluded_result_count": len(parsed_excluded_result_ids),
                "diversity_mode": resolved_diversity_mode,
                "flavor_direction": resolved_flavor_direction,
                "flavor_direction_policy": (
                    BEVERAGE_FLAVOR_DIRECTION_POLICY_V1
                    if resolved_flavor_direction
                    else None
                ),
                "feedback_policy": feedback_context.policy,
                "feedback_suppressed_count": len(feedback_context.suppressed_ids),
                "feedback_positive_count": len(feedback_context.positive_ids),
            },
        )
        self._session.add(request)
        self._session.flush()

        response_items: list[BeverageRecommendationItem] = []
        for index, (candidate, score) in enumerate(selected_ranked, start=1):
            model_features = beverage_model_features(
                profile=profile,
                candidate=candidate,
                score=score,
                scoring_config=scoring_config,
                flavor_direction=resolved_flavor_direction,
            )
            image_metadata = _beverage_image_metadata(candidate.beverage.metadata_json)
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
                    "image": image_metadata,
                    "model_features": model_features,
                    "request_controls": {
                        "diversity_mode": resolved_diversity_mode,
                        "flavor_direction": resolved_flavor_direction,
                        "flavor_direction_policy": (
                            BEVERAGE_FLAVOR_DIRECTION_POLICY_V1
                            if resolved_flavor_direction
                            else None
                        ),
                        "excluded_beverage_count": len(excluded_beverage_ids),
                        "feedback_policy": feedback_context.policy,
                        "feedback_suppressed_count": len(
                            feedback_context.suppressed_ids,
                        ),
                    },
                },
                qdrant_point_id=None,
            )
            self._session.add(result)
            self._session.flush()
            explanation = RecommendationExplanation(
                result_id=result.id,
                reason_codes=score.reason_codes,
                matched_dimensions_json=score.matched_dimensions,
                template_version=_beverage_template_version(scoring_config),
                explanation_text=score.explanation,
                debug_json={
                    "catalog_key": _catalog_key(candidate),
                    "qdrant_used": False,
                    "candidate_source": "postgres_catalog",
                    "template_version": _beverage_template_version(scoring_config),
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
                        "price_min_krw": candidate.beverage.price_min_krw,
                        "price_max_krw": candidate.beverage.price_max_krw,
                        "price_observation_summary": (
                            candidate.beverage.metadata_json.get(
                                "price_observation_summary",
                            )
                        ),
                        "price_policy": candidate.beverage.metadata_json.get(
                            "price_policy",
                        ),
                        "budget_tradeoff": model_features["budget_tradeoff"],
                        "image": image_metadata,
                        "image_url": image_metadata.get("image_url"),
                        "image_alt_text_ko": image_metadata.get("alt_text_ko"),
                        "image_attribution": image_metadata.get("attribution"),
                        "image_license": image_metadata.get("license"),
                        "candidate_source": "postgres_catalog",
                        "model_features": model_features,
                        "request_controls": {
                            "diversity_mode": resolved_diversity_mode,
                            "flavor_direction": resolved_flavor_direction,
                            "flavor_direction_policy": (
                                BEVERAGE_FLAVOR_DIRECTION_POLICY_V1
                                if resolved_flavor_direction
                                else None
                            ),
                            "excluded_beverage_count": len(excluded_beverage_ids),
                            "feedback_policy": feedback_context.policy,
                            "feedback_suppressed_count": len(
                                feedback_context.suppressed_ids,
                            ),
                        },
                    },
                ),
            )

        response = BeverageRecommendationResponse(
            request_id=request.id,
            profile_status=ProfileStatus.ACTIVE.value,
            profile_revision=profile.profile_revision,
            scoring_config_version=scoring_config.version,
            results=tuple(response_items),
        )
        _log_recommendation_completed(
            request_id=request.id,
            target_type=RecommendationTargetType.BEVERAGE.value,
            profile_revision=profile.profile_revision,
            scoring_config_version=scoring_config.version,
            vector_schema_version=_vector_schema_version(profile),
            result_count=len(response_items),
            latency_ms=_elapsed_ms(started_at),
            catalog_source_versions=_catalog_source_versions(
                candidate for candidate, _score in selected_ranked
            ),
        )
        return response

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
        place_types: tuple[str, ...] | list[str] | None = None,
        now: datetime | None = None,
    ) -> VenueRecommendationResponse:
        started_at = perf_counter()
        if budget_mode not in {"soft", "strict"}:
            raise ValueError("budget_mode must be soft or strict")
        selected_id = _parse_uuid(selected_beverage_id, "selected_beverage_id")
        requested_place_types, resolved_place_types = (
            _normalize_venue_place_type_filter(place_types)
        )
        _validate_coordinates(lat, lng)
        if radius_m is not None and radius_m <= 0:
            raise ValueError("radius_m must be greater than zero")
        resolved_radius = min(radius_m or DEFAULT_RADIUS_M, MAX_RADIUS_M)
        resolved_limit = min(max(limit or 3, 1), MAX_LIMIT)
        resolved_now = now or datetime.now(UTC)

        profile = self._profiles.get_active_profile_revision(external_user_id)
        if profile is None or profile.status != ProfileStatus.ACTIVE.value:
            status = self.get_profile_status(external_user_id)
            _log_recommendation_skipped(
                target_type=RecommendationTargetType.VENUE.value,
                profile_status=status.status,
                profile_revision=status.profile_revision,
                error_type="profile_not_active",
                latency_ms=_elapsed_ms(started_at),
            )
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

        scoring_config = _active_venue_scoring(
            self._session,
            self._active_scoring_config,
        )
        candidates = self._catalog.list_selected_beverage_venue_candidates(
            beverage_item_id=selected_id,
        )
        candidate_count_before_place_type_filter = len(candidates)
        candidates = _filter_venue_candidates_by_place_type(
            candidates,
            resolved_place_types,
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
            distance_provider=self._venue_distance_provider,
        )
        if budget_mode == "strict" and not ranked:
            raise RecommendationPreconditionError(
                "strict budget mode requires eligible venues with valid "
                "price snapshots",
            )

        distance_context = _venue_distance_request_context(ranked)
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
                "place_types": list(requested_place_types),
            },
            scoring_config_id=scoring_config.id,
            request_context_json={
                "pipeline": "postgres_selected_beverage_venue_v1",
                "qdrant_used": False,
                "place_type_filter_policy": "venue_snapshot_place_type_filter_v1",
                "resolved_place_types": list(resolved_place_types),
                "candidate_count_before_place_type_filter": (
                    candidate_count_before_place_type_filter
                ),
                "candidate_count_after_place_type_filter": len(candidates),
                **distance_context,
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
                    "distance_strategy": score.source_snapshot.get(
                        "distance_strategy",
                    ),
                    "distance_source": score.source_snapshot.get("distance_source"),
                    "is_route_distance": score.source_snapshot.get(
                        "is_route_distance",
                    ),
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

        response = VenueRecommendationResponse(
            request_id=request.id,
            profile_status=ProfileStatus.ACTIVE.value,
            profile_revision=profile.profile_revision,
            scoring_config_version=scoring_config.version,
            results=tuple(response_items),
        )
        _log_recommendation_completed(
            request_id=request.id,
            target_type=RecommendationTargetType.VENUE.value,
            profile_revision=profile.profile_revision,
            scoring_config_version=scoring_config.version,
            vector_schema_version=_vector_schema_version(profile),
            result_count=len(response_items),
            latency_ms=_elapsed_ms(started_at),
            map_snapshot_revisions=_map_snapshot_revisions(response_items),
        )
        return response

    def record_interaction(
        self,
        *,
        request_id: uuid.UUID,
        result_id: uuid.UUID | None,
        event_type: str,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> InteractionRecordResult:
        if event_type not in INTERACTION_EVENT_TYPES:
            raise ValueError(f"unsupported recommendation event type: {event_type}")
        resolved_idempotency_key = _normalize_idempotency_key(idempotency_key)
        sanitized_metadata = validate_interaction_metadata(metadata)
        if resolved_idempotency_key:
            existing = self._session.scalar(
                select(RecommendationInteraction).where(
                    RecommendationInteraction.idempotency_key
                    == resolved_idempotency_key,
                ),
            )
            if existing is not None:
                return InteractionRecordResult(existing.id, duplicate=True)
        interaction = RecommendationInteraction(
            request_id=request_id,
            result_id=result_id,
            event_type=event_type,
            idempotency_key=resolved_idempotency_key,
            metadata_json=sanitized_metadata,
        )
        self._session.add(interaction)
        self._session.flush()
        return InteractionRecordResult(interaction.id, duplicate=False)


def validate_interaction_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Return feedback metadata after enforcing the public allowlist."""

    if metadata is None:
        return {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")

    sanitized: dict[str, Any] = {}
    for raw_key, value in metadata.items():
        key = str(raw_key)
        normalized_key = key.lower().replace("-", "_")
        if _is_pii_like_metadata_key(normalized_key):
            raise ValueError(f"unsafe recommendation event metadata key: {key}")
        if key not in ALLOWED_INTERACTION_METADATA_KEYS:
            raise ValueError(f"unsupported recommendation event metadata key: {key}")
        if value is None:
            continue
        if key in INTERACTION_METADATA_STRING_KEYS:
            sanitized[key] = _metadata_string(key, value)
            continue
        if key in INTERACTION_METADATA_INTEGER_KEYS:
            sanitized[key] = _metadata_integer(key, value)
            continue
        raise ValueError(f"unsupported recommendation event metadata key: {key}")
    return sanitized


def _normalize_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("idempotency_key must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("idempotency_key must not be blank")
    if len(normalized) > 128:
        raise ValueError("idempotency_key must be at most 128 characters")
    return normalized


def _normalize_venue_place_type_filter(
    place_types: tuple[str, ...] | list[str] | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not place_types:
        return (), ()

    requested: list[str] = []
    resolved: set[str] = set()
    for raw_place_type in place_types:
        if not isinstance(raw_place_type, str):
            raise ValueError("place_types must contain strings")
        place_type = _normalize_venue_place_type_token(raw_place_type)
        if not place_type:
            raise ValueError("place_types must not contain blank values")
        if place_type not in VENUE_PLACE_TYPE_ALIASES:
            raise ValueError(f"unsupported venue place_type filter: {raw_place_type}")
        if place_type in requested:
            continue
        requested.append(place_type)
        resolved.update(VENUE_PLACE_TYPE_ALIASES[place_type])

    if len(requested) > MAX_VENUE_PLACE_TYPE_FILTERS:
        raise ValueError(
            f"place_types must contain at most {MAX_VENUE_PLACE_TYPE_FILTERS} values",
        )
    return tuple(requested), tuple(sorted(resolved))


def _filter_venue_candidates_by_place_type(
    candidates: tuple[VenueSnapshotCandidate, ...],
    resolved_place_types: tuple[str, ...],
) -> tuple[VenueSnapshotCandidate, ...]:
    if not resolved_place_types:
        return candidates
    allowed = set(resolved_place_types)
    return tuple(
        candidate
        for candidate in candidates
        if _normalize_venue_place_type_token(candidate.venue.place_type) in allowed
    )


def _normalize_venue_place_type_token(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _is_pii_like_metadata_key(key: str) -> bool:
    return any(token in key for token in PII_LIKE_INTERACTION_METADATA_TOKENS)


def _metadata_string(key: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"metadata.{key} must be a string")
    if len(value) > MAX_INTERACTION_METADATA_STRING_LENGTH:
        raise ValueError(
            f"metadata.{key} must be at most "
            f"{MAX_INTERACTION_METADATA_STRING_LENGTH} characters",
        )
    return value


def _metadata_integer(key: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"metadata.{key} must be an integer")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"metadata.{key} must be an integer")
    normalized = int(value)
    if normalized < 0:
        raise ValueError(f"metadata.{key} must be greater than or equal to zero")
    if normalized > MAX_INTERACTION_METADATA_INTEGER:
        raise ValueError(
            f"metadata.{key} must be less than or equal to "
            f"{MAX_INTERACTION_METADATA_INTEGER}",
        )
    return normalized


def score_beverage_candidate(
    *,
    profile: TasteProfileRevision,
    candidate: BeverageVectorCandidate,
    scoring_config: ScoringConfig,
    flavor_direction: str | None = None,
) -> ScoreComputation:
    weights = scoring_config.weights_json
    resolved_flavor_direction = _normalize_beverage_flavor_direction(
        flavor_direction,
    )
    similarity_feature = _beverage_similarity_feature(
        profile,
        candidate,
        scoring_config,
    )
    similarity = similarity_feature.similarity
    category_fit = _category_fit(profile, candidate)
    budget_feature = _beverage_budget_feature(profile, candidate)
    budget_fit = budget_feature.fit
    experience_fit = _experience_fit(profile, candidate)
    popularity_or_quality = _popularity_or_quality(candidate)
    diversity_adjustment = 0.5
    flavor_direction_feature = _beverage_flavor_direction_feature(
        resolved_flavor_direction,
        candidate,
    )
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
    if flavor_direction_feature is not None:
        breakdown["flavor_direction_adjustment"] = flavor_direction_feature.adjustment
    final_score = round(max(0.0, min(1.0, sum(breakdown.values()))), 6)
    matched_dimensions = _matched_dimensions(profile, candidate)
    reason_codes = _reason_codes(
        profile,
        candidate,
        matched_dimensions,
        budget_feature,
        flavor_direction_feature,
    )
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
    flavor_direction: str | None = None,
) -> dict[str, Any]:
    """Return model-ready, deterministic features used to score a beverage."""

    resolved_flavor_direction = _normalize_beverage_flavor_direction(
        flavor_direction,
    )
    budget_feature = _beverage_budget_feature(profile, candidate)
    budget_tradeoff = _beverage_budget_tradeoff_metadata(budget_feature)
    flavor_direction_feature = _beverage_flavor_direction_feature(
        resolved_flavor_direction,
        candidate,
    )
    return {
        "taste_similarity": score.similarity,
        "taste_similarity_feature": _beverage_similarity_feature(
            profile,
            candidate,
            scoring_config,
        ).as_dict(),
        "category_fit": round(_category_fit(profile, candidate), 6),
        "budget_fit": round(budget_feature.fit, 6),
        "budget_feature": budget_feature.as_dict(),
        "budget_tradeoff": budget_tradeoff,
        "experience_fit": round(_experience_fit(profile, candidate), 6),
        "popularity_or_quality": round(_popularity_or_quality(candidate), 6),
        "diversity_adjustment": 0.5,
        "flavor_direction_feature": (
            flavor_direction_feature.as_dict()
            if flavor_direction_feature is not None
            else None
        ),
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
    distance_provider: VenueDistanceProvider | None = None,
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
            distance_provider=distance_provider,
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
    distance_provider: VenueDistanceProvider | None = None,
) -> VenueScoreComputation | None:
    if not _venue_is_rankable(candidate):
        return None
    provider = distance_provider or DEFAULT_VENUE_DISTANCE_PROVIDER
    distance_feature = provider.distance_for(
        candidate,
        origin_lat=lat,
        origin_lng=lng,
        now=now,
    )
    if distance_feature is None:
        return None
    if not _is_valid_venue_distance_feature(distance_feature):
        logger.warning(
            "invalid venue distance feature; candidate skipped",
            extra={
                "structured": {
                    "event": "recommendation.invalid_distance_feature",
                    "place_id": candidate.venue.place_id,
                    "distance_strategy": distance_feature.strategy,
                    "distance_source": distance_feature.source,
                },
            },
        )
        return None
    distance_m = round(distance_feature.distance_m, 2)
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
        source_snapshot=_source_snapshot_metadata(candidate, distance_feature),
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


def _beverage_similarity_feature(
    profile: TasteProfileRevision,
    candidate: BeverageVectorCandidate,
    scoring_config: ScoringConfig,
) -> BeverageSimilarityFeature:
    rules = scoring_config.reason_code_rules_json or {}
    strategy = rules.get("similarity_strategy")
    if strategy != CATEGORY_WEIGHTED_SIMILARITY_V1:
        similarity = _cosine(profile.taste_vector, candidate.vector.vector)
        return BeverageSimilarityFeature(
            strategy=BEVERAGE_SIMILARITY_STRATEGY_COSINE,
            similarity=round(similarity, 6),
            category=candidate.beverage.category,
            dimension_weights={},
        )

    dimension_weights = _category_dimension_weights(candidate.beverage.category, rules)
    similarity = _weighted_cosine(
        profile.taste_vector,
        candidate.vector.vector,
        [
            dimension_weights.get(dimension.name, 1.0)
            for dimension in TASTE_V1_DIMENSIONS
        ],
    )
    return BeverageSimilarityFeature(
        strategy=CATEGORY_WEIGHTED_SIMILARITY_V1,
        similarity=round(similarity, 6),
        category=candidate.beverage.category,
        dimension_weights=dimension_weights,
    )


def _weighted_cosine(
    left: list[float],
    right: list[float],
    weights: list[float],
) -> float:
    if len(left) != len(right) or len(left) != len(weights):
        raise ValueError("vectors and weights must have the same dimension count")
    sanitized_weights = [max(0.0, float(weight)) for weight in weights]
    dot = sum(
        weight * a * b
        for a, b, weight in zip(left, right, sanitized_weights, strict=True)
    )
    left_norm = math.sqrt(
        sum(weight * a * a for a, weight in zip(left, sanitized_weights, strict=True)),
    )
    right_norm = math.sqrt(
        sum(weight * b * b for b, weight in zip(right, sanitized_weights, strict=True)),
    )
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


def _category_dimension_weights(
    category: str,
    rules: dict[str, Any],
) -> dict[str, float]:
    raw_by_category = rules.get("category_dimension_weights")
    if not isinstance(raw_by_category, dict):
        raw_by_category = CATEGORY_DIMENSION_WEIGHTS_V1
    raw_weights = raw_by_category.get(category)
    if not isinstance(raw_weights, dict):
        raw_weights = {}
    allowed_names = {dimension.name for dimension in TASTE_V1_DIMENSIONS}
    weights: dict[str, float] = {}
    for name, value in raw_weights.items():
        if name not in allowed_names or not isinstance(value, int | float):
            continue
        if value > 0:
            weights[name] = round(float(value), 6)
    return weights


def _beverage_flavor_direction_feature(
    flavor_direction: str | None,
    candidate: BeverageVectorCandidate,
) -> BeverageFlavorDirectionFeature | None:
    if flavor_direction is None:
        return None
    dimension_weights = BEVERAGE_FLAVOR_DIRECTION_DIMENSION_WEIGHTS[flavor_direction]
    total_weight = 0.0
    weighted_sum = 0.0
    for dimension_name, raw_weight in dimension_weights.items():
        weight = float(raw_weight)
        absolute_weight = abs(weight)
        if absolute_weight == 0:
            continue
        dimension_value = _candidate_dimension_value(candidate, dimension_name)
        direction_value = dimension_value if weight > 0 else 1.0 - dimension_value
        weighted_sum += absolute_weight * max(0.0, min(1.0, direction_value))
        total_weight += absolute_weight
    fit = round(weighted_sum / total_weight, 6) if total_weight else 0.5
    adjustment = round((fit - 0.5) * BEVERAGE_FLAVOR_DIRECTION_ADJUSTMENT_WEIGHT, 6)
    return BeverageFlavorDirectionFeature(
        policy=BEVERAGE_FLAVOR_DIRECTION_POLICY_V1,
        direction=flavor_direction,
        fit=fit,
        adjustment=adjustment,
        dimension_weights={
            dimension: round(float(weight), 6)
            for dimension, weight in dimension_weights.items()
        },
    )


def _candidate_dimension_value(
    candidate: BeverageVectorCandidate,
    dimension_name: str,
) -> float:
    raw_value = candidate.vector.vector_json.get(dimension_name)
    if isinstance(raw_value, int | float) and not isinstance(raw_value, bool):
        return max(0.0, min(1.0, float(raw_value)))
    for dimension in TASTE_V1_DIMENSIONS:
        if dimension.name != dimension_name:
            continue
        if dimension.index >= len(candidate.vector.vector):
            return 0.0
        return max(0.0, min(1.0, float(candidate.vector.vector[dimension.index])))
    return 0.0


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


def _beverage_budget_feature(
    profile: TasteProfileRevision,
    candidate: BeverageVectorCandidate,
) -> BeverageBudgetFeature:
    price_min = candidate.beverage.price_min_krw
    price_max = candidate.beverage.price_max_krw
    floor, ceiling = _budget_bounds_krw(profile.budget_range)
    price_policy = _metadata_string_or_none(
        candidate.beverage.metadata_json.get("price_policy"),
    )
    if (
        profile.budget_range is None
        or price_min is None
        or price_max is None
        or price_min <= 0
        or price_max <= 0
        or price_min > price_max
    ):
        return BeverageBudgetFeature(
            strategy=BEVERAGE_BUDGET_STRATEGY_CATALOG_PRICE_SOFT,
            fit=NEUTRAL_BUDGET_FIT,
            confidence=0.0,
            evidence="missing_price_or_budget",
            budget_range=profile.budget_range,
            budget_floor_krw=floor,
            budget_ceiling_krw=ceiling,
            price_min_krw=price_min,
            price_max_krw=price_max,
            price_mid_krw=None,
            price_policy=price_policy,
        )

    price_mid = round((price_min + price_max) / 2, 2)
    raw_fit = _raw_catalog_price_budget_fit(
        price_min=price_min,
        price_max=price_max,
        price_mid=price_mid,
        budget_floor=floor,
        budget_ceiling=ceiling,
    )
    confidence = _catalog_price_confidence(candidate)
    fit = round(
        (raw_fit * confidence) + (NEUTRAL_BUDGET_FIT * (1.0 - confidence)),
        6,
    )
    return BeverageBudgetFeature(
        strategy=BEVERAGE_BUDGET_STRATEGY_CATALOG_PRICE_SOFT,
        fit=fit,
        confidence=confidence,
        evidence="catalog_price_range",
        budget_range=profile.budget_range,
        budget_floor_krw=floor,
        budget_ceiling_krw=ceiling,
        price_min_krw=price_min,
        price_max_krw=price_max,
        price_mid_krw=price_mid,
        price_policy=price_policy,
    )


def _beverage_budget_tradeoff_metadata(
    budget_feature: BeverageBudgetFeature,
) -> dict[str, Any]:
    status, label_ko, note_ko = _beverage_budget_tradeoff_text(budget_feature)
    return {
        "policy_version": BEVERAGE_BUDGET_TRADEOFF_POLICY_V1,
        "status": status,
        "display_label_ko": label_ko,
        "note_ko": note_ko,
        "budget_range": budget_feature.budget_range,
        "budget_floor_krw": budget_feature.budget_floor_krw,
        "budget_ceiling_krw": budget_feature.budget_ceiling_krw,
        "price_min_krw": budget_feature.price_min_krw,
        "price_max_krw": budget_feature.price_max_krw,
        "price_mid_krw": budget_feature.price_mid_krw,
        "fit": budget_feature.fit,
        "confidence": budget_feature.confidence,
        "evidence": budget_feature.evidence,
        "price_policy": budget_feature.price_policy,
        "source": "catalog_price_not_live_offer",
    }


def _beverage_budget_tradeoff_text(
    budget_feature: BeverageBudgetFeature,
) -> tuple[str, str, str]:
    if budget_feature.evidence == "missing_price_or_budget":
        return (
            "missing_price_or_budget",
            "가격 판단 보류",
            "예산 또는 검증된 카탈로그 가격대가 부족해 가격은 중립적으로 반영했습니다.",
        )

    price_mid = budget_feature.price_mid_krw
    floor = budget_feature.budget_floor_krw
    ceiling = budget_feature.budget_ceiling_krw
    if price_mid is None:
        return (
            "missing_price_or_budget",
            "가격 판단 보류",
            "검증된 카탈로그 가격대가 부족해 가격은 중립적으로 반영했습니다.",
        )

    if floor is None and ceiling is not None:
        if budget_feature.price_min_krw is not None and (
            budget_feature.price_min_krw > ceiling
        ):
            return (
                "above_budget_soft_tradeoff",
                "예산 초과 가능",
                "카탈로그 가격대가 선택한 예산보다 높지만, "
                "취향 일치도를 함께 고려한 소프트 추천입니다.",
            )
        if price_mid <= ceiling:
            return (
                "within_budget",
                "예산 적합",
                "검증된 카탈로그 가격대 기준으로 선택한 예산과 잘 맞습니다.",
            )
        return (
            "near_budget_soft_tradeoff",
            "예산 근접",
            "카탈로그 중간 가격은 예산을 조금 넘지만, "
            "일부 가격대와 취향 적합도를 함께 고려했습니다.",
        )

    if floor is not None and ceiling is not None:
        price_min = budget_feature.price_min_krw
        price_max = budget_feature.price_max_krw
        if price_min is not None and price_max is not None and (
            price_min <= ceiling and price_max >= floor
        ):
            return (
                "within_budget",
                "예산 적합",
                "검증된 카탈로그 가격대가 선택한 예산 구간과 겹칩니다.",
            )
        if price_mid > ceiling:
            return (
                "above_budget_soft_tradeoff",
                "예산 초과 가능",
                "카탈로그 가격대가 선택한 예산 구간보다 높지만, "
                "취향 일치도를 함께 고려한 소프트 추천입니다.",
            )
        return (
            "below_budget_floor_soft_tradeoff",
            "예산보다 낮은 가격대",
            "선택한 예산 구간보다 낮은 가격대지만, 취향 일치도를 우선해 추천했습니다.",
        )

    if floor is not None and ceiling is None:
        if price_mid >= floor:
            return (
                "premium_tolerant_match",
                "프리미엄 예산 적합",
                "프리미엄 허용 예산과 검증된 카탈로그 가격대가 잘 맞습니다.",
            )
        return (
            "below_premium_budget",
            "예산보다 낮은 가격대",
            "프리미엄 예산을 허용했지만, "
            "이 추천은 더 낮은 가격대에서 취향 일치도가 높습니다.",
        )

    return (
        "neutral_budget",
        "예산 중립",
        "예산 조건이 명확하지 않아 가격 신호는 중립적으로 반영했습니다.",
    )


def _budget_bounds_krw(budget_range: str | None) -> tuple[int | None, int | None]:
    if not budget_range:
        return None, None
    if budget_range.startswith("under_"):
        return None, _parse_positive_int(budget_range.removeprefix("under_"))
    if budget_range.startswith("over_"):
        return _parse_positive_int(budget_range.removeprefix("over_")), None
    parts = budget_range.split("_", 1)
    if len(parts) != 2:
        return None, None
    floor = _parse_positive_int(parts[0])
    ceiling = _parse_positive_int(parts[1])
    if floor is not None and ceiling is not None and floor > ceiling:
        return None, None
    return floor, ceiling


def _parse_positive_int(value: str) -> int | None:
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _raw_catalog_price_budget_fit(
    *,
    price_min: int,
    price_max: int,
    price_mid: float,
    budget_floor: int | None,
    budget_ceiling: int | None,
) -> float:
    if budget_floor is None and budget_ceiling is None:
        return NEUTRAL_BUDGET_FIT
    if budget_ceiling is not None and budget_floor is None:
        if price_min <= budget_ceiling:
            return 1.0 if price_mid <= budget_ceiling else 0.9
        return max(0.1, min(0.9, budget_ceiling / price_mid))
    if budget_floor is not None and budget_ceiling is not None:
        if price_min <= budget_ceiling and price_max >= budget_floor:
            return 1.0
        if price_mid < budget_floor:
            return 0.85
        return max(0.1, min(0.9, budget_ceiling / price_mid))
    if budget_floor is not None and budget_ceiling is None:
        if price_mid >= budget_floor:
            return 1.0
        if price_mid >= budget_floor * 0.5:
            return 0.85
        return 0.65
    return NEUTRAL_BUDGET_FIT


def _catalog_price_confidence(candidate: BeverageVectorCandidate) -> float:
    summary = candidate.beverage.metadata_json.get("price_observation_summary")
    observation_count = 0
    if isinstance(summary, dict):
        raw_count = summary.get("observation_count")
        if isinstance(raw_count, int | float) and raw_count > 0:
            observation_count = int(raw_count)
    confidence = min(0.85, 0.45 + (0.10 * observation_count))
    if (
        candidate.beverage.metadata_json.get("price_policy")
        != BEVERAGE_PRICE_POLICY_VERIFIED_KRW
    ):
        confidence *= 0.8
    return round(max(0.25, min(0.85, confidence)), 6)


def _metadata_string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


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
    budget_feature: BeverageBudgetFeature,
    flavor_direction_feature: BeverageFlavorDirectionFeature | None = None,
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
    if (
        budget_feature.evidence != "missing_price_or_budget"
        and budget_feature.confidence >= 0.4
        and budget_feature.fit >= 0.72
    ):
        reason_codes.add("WITHIN_BUDGET")
    if (
        flavor_direction_feature is not None
        and flavor_direction_feature.fit >= 0.6
    ):
        reason_codes.add("MATCHES_REQUESTED_FLAVOR_DIRECTION")
    return _sort_beverage_reason_codes(reason_codes)


def _sort_beverage_reason_codes(reason_codes: set[str] | list[str]) -> list[str]:
    priority = {code: index for index, code in enumerate(BEVERAGE_REASON_PRIORITY)}
    return sorted(
        reason_codes,
        key=lambda code: (priority.get(code, len(priority)), code),
    )


def _beverage_template_version(scoring_config: ScoringConfig) -> str:
    template_version = scoring_config.reason_code_rules_json.get("template_version")
    if isinstance(template_version, str) and template_version:
        return template_version
    return "reason_template_v1"


def _explanation(
    candidate: BeverageVectorCandidate,
    reason_codes: list[str],
) -> str:
    display_name = candidate.beverage.name_ko or candidate.beverage.name_en or "이 술"
    style = _style(candidate)
    lead = f"{display_name}은(는) 현재 취향 프로필과 잘 맞는 추천입니다."
    if style:
        lead = (
            f"{display_name}은(는) {style} 계열로, "
            "현재 취향 프로필과 잘 맞는 추천입니다."
        )

    reason_sentences = [
        BEVERAGE_REASON_TEXT_KO[code][1]
        for code in _sort_beverage_reason_codes(reason_codes)
        if code in BEVERAGE_REASON_TEXT_KO
    ][:3]
    if not reason_codes:
        return f"{lead} 검증된 카탈로그 맛 프로필 기준으로 가장 가까운 후보입니다."
    if not reason_sentences:
        return f"{lead} 추천 사유 코드는 결과 메타데이터에 함께 기록됩니다."
    return f"{lead} " + " ".join(f"{reason}." for reason in reason_sentences)


def _catalog_key(candidate: BeverageVectorCandidate) -> str:
    value = candidate.beverage.metadata_json.get("catalog_key")
    return value if isinstance(value, str) else str(candidate.beverage.id)


def _style(candidate: BeverageVectorCandidate) -> str | None:
    value = candidate.beverage.metadata_json.get("style")
    return value if isinstance(value, str) else None


def _beverage_image_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    image = metadata.get("image")
    if isinstance(image, dict) and isinstance(image.get("image_url"), str):
        return {key: value for key, value in image.items() if value is not None}

    image_url = metadata.get("image_url")
    if not isinstance(image_url, str) or not image_url:
        return {}

    return {
        "policy_version": metadata.get("image_policy_version", "unknown"),
        "image_kind": metadata.get("image_kind"),
        "image_url": image_url,
        "alt_text_ko": metadata.get("image_alt_text_ko"),
        "source_url": metadata.get("image_source_url"),
        "license": metadata.get("image_license"),
        "attribution": metadata.get("image_attribution"),
        "display_policy": metadata.get("image_display_policy"),
        "review_status": metadata.get("image_review_status"),
    }


def _normalize_beverage_diversity_mode(value: str | None) -> str:
    if value is None or value == "":
        return BEVERAGE_DIVERSITY_STANDARD
    normalized = value.strip().lower()
    if normalized not in BEVERAGE_DIVERSITY_MODES:
        raise ValueError("diversity_mode must be standard, different, or adjacent")
    return normalized


def _normalize_beverage_flavor_direction(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    normalized = value.strip().lower()
    if normalized not in BEVERAGE_FLAVOR_DIRECTION_MODES:
        supported = ", ".join(sorted(BEVERAGE_FLAVOR_DIRECTION_MODES))
        raise ValueError(
            f"flavor_direction must be one of: {supported}",
        )
    return normalized


def _parse_uuid_values(values: list[str] | None, field_name: str) -> set[uuid.UUID]:
    if not values:
        return set()
    if len(values) > MAX_EXCLUDE_IDS:
        raise ValueError(f"{field_name} must include at most {MAX_EXCLUDE_IDS} ids")
    parsed: set[uuid.UUID] = set()
    for value in values:
        parsed.add(_parse_uuid(str(value), field_name))
    return parsed


def _beverage_ids_from_result_ids(
    session: Session,
    result_ids: set[uuid.UUID],
) -> set[uuid.UUID]:
    if not result_ids:
        return set()
    rows = session.execute(
        select(RecommendationResult.target_id).where(
            RecommendationResult.id.in_(result_ids),
            RecommendationResult.target_type == RecommendationTargetType.BEVERAGE.value,
        ),
    ).all()
    beverage_ids: set[uuid.UUID] = set()
    for row in rows:
        try:
            beverage_ids.add(uuid.UUID(str(row[0])))
        except ValueError:
            logger.warning(
                "recommendation result target_id is not a beverage UUID",
                extra={
                    "structured": {
                        "event": "recommendation.invalid_result_target_id",
                        "target_type": RecommendationTargetType.BEVERAGE.value,
                    },
                },
            )
    return beverage_ids


def _beverage_feedback_context(
    session: Session,
    external_user_id: str,
) -> BeverageFeedbackContext:
    rows = session.execute(
        select(
            RecommendationResult.target_id,
            RecommendationInteraction.event_type,
        )
        .join(
            RecommendationRequest,
            RecommendationRequest.id == RecommendationResult.request_id,
        )
        .join(
            RecommendationInteraction,
            RecommendationInteraction.result_id == RecommendationResult.id,
        )
        .where(
            RecommendationRequest.external_user_id == external_user_id,
            RecommendationResult.target_type == RecommendationTargetType.BEVERAGE.value,
            RecommendationInteraction.event_type.in_(
                [
                    InteractionEventType.DISMISS.value,
                    *sorted(BEVERAGE_FEEDBACK_POSITIVE_EVENTS),
                ],
            ),
        )
        .order_by(RecommendationInteraction.created_at.desc())
        .limit(MAX_EXCLUDE_IDS * 4),
    ).all()
    latest_event_by_beverage: dict[uuid.UUID, str] = {}
    for row in rows:
        try:
            beverage_id = uuid.UUID(str(row[0]))
        except ValueError:
            continue
        if beverage_id in latest_event_by_beverage:
            continue
        latest_event_by_beverage[beverage_id] = str(row[1])

    positive_ids = {
        beverage_id
        for beverage_id, event_type in latest_event_by_beverage.items()
        if event_type in BEVERAGE_FEEDBACK_POSITIVE_EVENTS
    }
    suppressed_ids = {
        beverage_id
        for beverage_id, event_type in latest_event_by_beverage.items()
        if event_type == InteractionEventType.DISMISS.value
    }
    suppressed_ids -= positive_ids
    return BeverageFeedbackContext(
        policy=BEVERAGE_FEEDBACK_POLICY_RECENT_DISMISS,
        suppressed_ids=suppressed_ids,
        positive_ids=positive_ids,
    )


def _beverage_exclusion_context(
    ranked: list[tuple[BeverageVectorCandidate, ScoreComputation]],
    excluded_beverage_ids: set[uuid.UUID],
) -> dict[str, set[str]]:
    styles: set[str] = set()
    categories: set[str] = set()
    if not excluded_beverage_ids:
        return {"styles": styles, "categories": categories}
    for candidate, _score in ranked:
        if candidate.beverage.id not in excluded_beverage_ids:
            continue
        style = _style(candidate)
        if style:
            styles.add(style)
        if candidate.beverage.category:
            categories.add(candidate.beverage.category)
    return {"styles": styles, "categories": categories}


def _select_beverage_recommendations(
    *,
    ranked: list[tuple[BeverageVectorCandidate, ScoreComputation]],
    profile: TasteProfileRevision,
    diversity_mode: str,
    excluded_styles: set[str],
    excluded_categories: set[str],
    category_filter: str | None,
    limit: int,
) -> tuple[tuple[BeverageVectorCandidate, ScoreComputation], ...]:
    if diversity_mode == BEVERAGE_DIVERSITY_STANDARD or not ranked:
        return tuple(ranked[:limit])
    if not excluded_styles and not excluded_categories:
        return tuple(ranked[:limit])

    adjacent_categories = {
        category
        for category in {
            *excluded_categories,
            *set(profile.preferred_categories or []),
            *(set([category_filter]) if category_filter else set()),
        }
        if category
    }
    if diversity_mode == BEVERAGE_DIVERSITY_DIFFERENT:
        predicates = (
            lambda candidate: _style(candidate) not in excluded_styles
            and (
                bool(category_filter)
                or candidate.beverage.category not in excluded_categories
            ),
            lambda candidate: _style(candidate) not in excluded_styles,
            lambda candidate: candidate.beverage.category not in excluded_categories,
            lambda candidate: True,
        )
    elif diversity_mode == BEVERAGE_DIVERSITY_ADJACENT:
        predicates = (
            lambda candidate: _style(candidate) not in excluded_styles
            and (
                not adjacent_categories
                or candidate.beverage.category in adjacent_categories
            ),
            lambda candidate: _style(candidate) not in excluded_styles,
            lambda candidate: True,
        )
    else:
        raise ValueError("diversity_mode must be standard, different, or adjacent")

    selected: dict[uuid.UUID, tuple[BeverageVectorCandidate, ScoreComputation]] = {}
    for predicate in predicates:
        for candidate, score in ranked:
            if len(selected) >= limit:
                return tuple(selected.values())
            if candidate.beverage.id in selected:
                continue
            if predicate(candidate):
                selected[candidate.beverage.id] = (candidate, score)
    return tuple(selected.values())


def _sorted_uuid_strings(values: set[uuid.UUID]) -> list[str]:
    return sorted(str(value) for value in values)


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
    distance_feature: VenueDistanceFeature,
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
        "distance_m": distance_feature.distance_m,
        "distance_strategy": distance_feature.strategy,
        "distance_source": distance_feature.source,
        "distance_confidence": distance_feature.confidence,
        "is_route_distance": distance_feature.is_route_distance,
        "distance_fallback_used": distance_feature.fallback_used,
        "straight_line_distance_m": distance_feature.straight_line_distance_m,
        "route_distance_m": distance_feature.route_distance_m,
        "route_duration_seconds": distance_feature.route_duration_seconds,
        "route_complexity": distance_feature.route_complexity,
    }


def _venue_distance_request_context(
    ranked: tuple[RankedVenueCandidate, ...],
) -> dict[str, Any]:
    distance_metadata = [item.score.source_snapshot for item in ranked]
    strategy_counts = Counter(
        str(metadata.get("distance_strategy"))
        for metadata in distance_metadata
        if metadata.get("distance_strategy")
    )
    source_counts = Counter(
        str(metadata.get("distance_source"))
        for metadata in distance_metadata
        if metadata.get("distance_source")
    )
    strategies = sorted(
        strategy_counts,
    )
    sources = sorted(
        source_counts,
    )
    result_count = len(distance_metadata)
    route_distance_count = sum(
        1 for metadata in distance_metadata if metadata.get("is_route_distance") is True
    )
    straight_line_distance_count = strategy_counts.get(
        DISTANCE_STRATEGY_STRAIGHT_LINE_MVP,
        0,
    )
    fallback_distance_count = sum(
        1
        for metadata in distance_metadata
        if metadata.get("distance_fallback_used") is True
    )
    unknown_distance_count = max(
        0,
        result_count - route_distance_count - straight_line_distance_count,
    )
    is_route_distance = any(
        metadata.get("is_route_distance") is True for metadata in distance_metadata
    )
    return {
        "distance_strategy": (
            "no_distance_results"
            if not strategies
            else strategies[0]
            if len(strategies) == 1
            else "mixed_distance_strategy"
        ),
        "distance_strategies": strategies,
        "distance_sources": sources,
        "is_route_distance": is_route_distance,
        "distance_provider_policy": "service_injected_provider_v1",
        "distance_result_count": result_count,
        "route_distance_result_count": route_distance_count,
        "straight_line_distance_result_count": straight_line_distance_count,
        "fallback_distance_result_count": fallback_distance_count,
        "unknown_distance_result_count": unknown_distance_count,
        "distance_route_coverage": (
            round(route_distance_count / result_count, 6) if result_count else 0.0
        ),
        "distance_strategy_counts": dict(sorted(strategy_counts.items())),
        "distance_source_counts": dict(sorted(source_counts.items())),
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


def _log_recommendation_completed(
    *,
    request_id: uuid.UUID,
    target_type: str,
    profile_revision: int,
    scoring_config_version: str,
    vector_schema_version: str,
    result_count: int,
    latency_ms: float,
    catalog_source_versions: list[str] | None = None,
    map_snapshot_revisions: list[dict[str, Any]] | None = None,
) -> None:
    runtime_metrics.record(
        f"{target_type}_recommendation",
        latency_ms=latency_ms,
    )
    payload: dict[str, Any] = {
        "event": "recommendation.completed",
        "request_id": str(request_id),
        "target_type": target_type,
        "profile_revision": profile_revision,
        "scoring_config": scoring_config_version,
        "vector_schema": vector_schema_version,
        "result_count": result_count,
        "latency_ms": latency_ms,
    }
    if catalog_source_versions is not None:
        payload["catalog_source_versions"] = catalog_source_versions
    if map_snapshot_revisions is not None:
        payload["map_snapshot_revisions"] = map_snapshot_revisions
    logger.info("recommendation request completed", extra={"structured": payload})


def _log_recommendation_skipped(
    *,
    target_type: str,
    profile_status: str,
    profile_revision: int | None,
    error_type: str,
    latency_ms: float,
) -> None:
    runtime_metrics.record(
        f"{target_type}_recommendation",
        latency_ms=latency_ms,
    )
    logger.info(
        "recommendation request skipped",
        extra={
            "structured": {
                "event": "recommendation.skipped",
                "target_type": target_type,
                "profile_status": profile_status,
                "profile_revision": profile_revision,
                "error_type": error_type,
                "result_count": 0,
                "latency_ms": latency_ms,
            },
        },
    )


def _catalog_source_versions(
    candidates: Any,
) -> list[str]:
    versions = {
        str(candidate.beverage.metadata_json.get("source_version"))
        for candidate in candidates
        if candidate.beverage.metadata_json.get("source_version")
    }
    return sorted(versions)


def _map_snapshot_revisions(
    items: list[VenueRecommendationItem],
) -> list[dict[str, Any]]:
    revisions: list[dict[str, Any]] = []
    for item in items:
        revisions.append(
            {
                "place_id": item.place_id,
                "place_revision": item.source_metadata.get("place_revision"),
                "menu_revision": item.source_metadata.get("menu_revision"),
                "inventory_revision": item.source_metadata.get("inventory_revision"),
                "price_revision": item.source_metadata.get("price_revision"),
            },
        )
    return revisions


def _vector_schema_version(profile: TasteProfileRevision) -> str:
    version = getattr(profile.vector_schema_version, "version", None)
    return str(version or profile.vector_schema_version_id)


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _iso(value: datetime | None) -> str | None:
    aware = _aware(value)
    return aware.isoformat() if aware else None


def _active_beverage_scoring(session: Session, version: str) -> ScoringConfig:
    scoring = session.scalar(
        select(ScoringConfig).where(
            ScoringConfig.version == version,
            ScoringConfig.target_type == RecommendationTargetType.BEVERAGE.value,
            ScoringConfig.category == "all",
            ScoringConfig.status == "active",
        ),
    )
    if scoring is None:
        raise ValueError(f"active beverage {version} config is missing")
    return scoring


def _active_venue_scoring(session: Session, version: str) -> ScoringConfig:
    scoring = session.scalar(
        select(ScoringConfig).where(
            ScoringConfig.version == version,
            ScoringConfig.target_type == RecommendationTargetType.VENUE.value,
            ScoringConfig.category == "all",
            ScoringConfig.status == "active",
        ),
    )
    if scoring is None:
        raise ValueError(f"active venue {version} config is missing")
    return scoring
