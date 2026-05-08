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
    VENUE = "venue"
    VENUE_MENU_ITEM = "venue_menu_item"
    FLAVOR_PROFILE = "flavor_profile"


class FlavorProfileOwnerType(StrEnum):
    BEVERAGE_ITEM = "beverage_item"
    VENUE = "venue"
    VENUE_MENU_ITEM = "venue_menu_item"


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

