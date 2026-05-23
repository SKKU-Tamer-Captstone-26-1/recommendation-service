from enum import StrEnum


class ArtifactStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class ProfileStatus(StrEnum):
    MISSING = "missing"
    PENDING_GENERATION = "pending_generation"
    ACTIVE = "active"
    STALE = "stale"
    REGENERATING = "regenerating"
    FAILED_GENERATION = "failed_generation"


class DistanceMetric(StrEnum):
    COSINE = "cosine"
    DOT = "dot"
    EUCLIDEAN = "euclidean"


class VectorOwnerType(StrEnum):
    PROFILE_REVISION = "profile_revision"
    BEVERAGE_ITEM = "beverage_item"
    VENUE_SNAPSHOT = "venue_snapshot"
    VENUE_MENU_SNAPSHOT = "venue_menu_snapshot"
    FLAVOR_PROFILE = "flavor_profile"


class FlavorProfileOwnerType(StrEnum):
    BEVERAGE_ITEM = "beverage_item"
    VENUE_SNAPSHOT = "venue_snapshot"
    VENUE_MENU_SNAPSHOT = "venue_menu_snapshot"


class RecommendationTargetType(StrEnum):
    BEVERAGE = "beverage"
    VENUE = "venue"
    MENU_ITEM = "menu_item"


class QdrantIndexStatus(StrEnum):
    PENDING = "pending"
    INDEXED = "indexed"
    FAILED = "failed"
    STALE = "stale"


class SyncEventStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    RETRY = "retry"
    DEAD_LETTER = "dead_letter"


class RebuildJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class InteractionEventType(StrEnum):
    IMPRESSION = "impression"
    CLICK = "click"
    SAVE = "save"
    DISMISS = "dismiss"
    DETAIL_VIEW = "detail_view"


class VenueOptionType(StrEnum):
    NEAREST_REASONABLE = "nearest_reasonable"
    BEST_PRICE = "best_price"
    BALANCED_BEST = "balanced_best"


class VenueAvailabilityStatus(StrEnum):
    AVAILABLE = "available"
    LIKELY_AVAILABLE = "likely_available"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


class VenueFreshnessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    EXPIRED = "expired"
