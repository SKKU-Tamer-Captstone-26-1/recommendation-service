from __future__ import annotations

import json
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.vector_schema import TASTE_V1_DIMENSIONS, TASTE_V1_NAME
from app.models.catalog import BeverageItem, FlavorProfile
from app.models.enums import FlavorProfileOwnerType, VectorOwnerType
from app.models.vector import RecommendationVector
from app.services.beverage_import import CanonicalSeedRecord

CRITICAL = "critical"
WARNING = "warning"
INFO = "info"

REQUIRED_METADATA_KEYS = (
    "catalog_key",
    "style",
    "source_type",
    "source_version",
    "curation_status",
)

WARNING_METADATA_KEYS = (
    "aliases_en",
    "aliases_ko",
    "serving_context",
)
REQUIRED_IMAGE_FIELDS = (
    "policy_version",
    "image_candidate_id",
    "image_kind",
    "image_url",
    "original_image_url",
    "cache_key",
    "cache_policy",
    "display_url_source",
    "alt_text_ko",
    "source_url",
    "source_type",
    "license",
    "license_url",
    "attribution",
    "display_policy",
    "review_status",
)
ALLOWED_IMAGE_POLICY_VERSIONS = frozenset({"beverage_image_v1"})
ALLOWED_IMAGE_DISPLAY_POLICIES = frozenset(
    {"allowed_mvp_display_with_license_metadata"},
)
ALLOWED_IMAGE_REVIEW_STATUSES = frozenset(
    {"source_checked_mvp_seed", "operator_approved"},
)
ALLOWED_IMAGE_CACHE_POLICIES = frozenset({"operator_managed_image_cache_v1"})
ALLOWED_IMAGE_DISPLAY_URL_SOURCES = frozenset(
    {"licensed_source_url", "operator_managed_cache"},
)


@dataclass(frozen=True)
class CatalogAuditIssue:
    severity: str
    code: str
    message: str
    beverage_id: str | None = None
    catalog_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "beverage_id": self.beverage_id,
            "catalog_key": self.catalog_key,
        }


@dataclass(frozen=True)
class CatalogAuditReport:
    generated_at: str
    source: str
    metrics: dict[str, Any]
    issues: tuple[CatalogAuditIssue, ...]

    @property
    def critical_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == WARNING)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "source": self.source,
            "metrics": self.metrics,
            "issues": [issue.to_dict() for issue in self.issues],
        }


class BeverageCatalogAuditService:
    """Audits recommendation-owned beverage catalog quality."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def audit_active_catalog(self) -> CatalogAuditReport:
        beverages = tuple(
            self._session.scalars(
                select(BeverageItem)
                .where(BeverageItem.active.is_(True))
                .order_by(BeverageItem.category, BeverageItem.name_en, BeverageItem.id),
            ).all(),
        )
        owner_ids = [beverage.id for beverage in beverages]
        if not owner_ids:
            return audit_catalog_rows(
                beverages=(),
                vectors=(),
                flavor_profiles=(),
                source="database:active_beverages",
            )

        vectors = tuple(
            self._session.scalars(
                select(RecommendationVector)
                .where(
                    RecommendationVector.owner_type
                    == VectorOwnerType.BEVERAGE_ITEM.value,
                    RecommendationVector.owner_id.in_(owner_ids),
                )
                .order_by(RecommendationVector.owner_id, RecommendationVector.id),
            ).all(),
        )
        flavor_profiles = tuple(
            self._session.scalars(
                select(FlavorProfile)
                .where(
                    FlavorProfile.owner_type
                    == FlavorProfileOwnerType.BEVERAGE_ITEM.value,
                    FlavorProfile.owner_id.in_(owner_ids),
                )
                .order_by(FlavorProfile.owner_id, FlavorProfile.id),
            ).all(),
        )
        return audit_catalog_rows(
            beverages=beverages,
            vectors=vectors,
            flavor_profiles=flavor_profiles,
            source="database:active_beverages",
        )


def audit_seed_records(
    records: tuple[CanonicalSeedRecord, ...],
    *,
    source: str = "seed_records",
) -> CatalogAuditReport:
    return audit_catalog_rows(
        beverages=tuple(record.beverage for record in records),
        vectors=tuple(record.vector for record in records),
        flavor_profiles=tuple(record.flavor_profile for record in records),
        source=source,
    )


def audit_catalog_rows(
    *,
    beverages: tuple[BeverageItem, ...],
    vectors: tuple[RecommendationVector, ...],
    flavor_profiles: tuple[FlavorProfile, ...],
    source: str,
    generated_at: datetime | None = None,
) -> CatalogAuditReport:
    issues: list[CatalogAuditIssue] = []
    vector_by_owner = _group_by_owner(vectors)
    flavor_by_owner = _group_by_owner(flavor_profiles)
    catalog_keys: Counter[str] = Counter()
    dimension_names = {dimension.name for dimension in TASTE_V1_DIMENSIONS}
    category_counts: Counter[str] = Counter()
    style_counts: Counter[str] = Counter()

    for beverage in sorted(beverages, key=_beverage_sort_key):
        metadata = beverage.metadata_json or {}
        catalog_key = _optional_string(metadata.get("catalog_key"))
        issue_context = {
            "beverage_id": str(beverage.id),
            "catalog_key": catalog_key,
        }
        category_counts[beverage.category] += 1
        if catalog_key:
            catalog_keys[catalog_key] += 1
        style = _optional_string(metadata.get("style"))
        if style:
            style_counts[style] += 1

        _audit_beverage_metadata(
            beverage,
            metadata,
            issue_context,
            issues,
        )
        _audit_flavor_profile(
            beverage,
            flavor_by_owner.get(beverage.id, ()),
            issue_context,
            issues,
            dimension_names,
        )
        _audit_vectors(
            beverage,
            vector_by_owner.get(beverage.id, ()),
            issue_context,
            issues,
            dimension_names,
        )

    for catalog_key, count in sorted(catalog_keys.items()):
        if count > 1:
            issues.append(
                CatalogAuditIssue(
                    severity=CRITICAL,
                    code="duplicate_catalog_key",
                    message=f"catalog_key appears {count} times",
                    catalog_key=catalog_key,
                ),
            )

    metrics = _metrics(
        beverages=beverages,
        vectors=vectors,
        flavor_profiles=flavor_profiles,
        category_counts=category_counts,
        style_counts=style_counts,
        issues=issues,
    )
    timestamp = (generated_at or datetime.now(UTC)).isoformat()
    return CatalogAuditReport(
        generated_at=timestamp,
        source=source,
        metrics=metrics,
        issues=tuple(sorted(issues, key=_issue_sort_key)),
    )


def write_catalog_audit_report(report: CatalogAuditReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )


def _audit_beverage_metadata(
    beverage: BeverageItem,
    metadata: dict[str, Any],
    issue_context: dict[str, str | None],
    issues: list[CatalogAuditIssue],
) -> None:
    for key in REQUIRED_METADATA_KEYS:
        value = metadata.get(key)
        if not _has_value(value):
            issues.append(
                CatalogAuditIssue(
                    severity=CRITICAL,
                    code=f"missing_metadata_{key}",
                    message=f"active beverage is missing metadata_json.{key}",
                    **issue_context,
                ),
            )

    for key in WARNING_METADATA_KEYS:
        value = metadata.get(key)
        if not _has_value(value):
            issues.append(
                CatalogAuditIssue(
                    severity=WARNING,
                    code=f"missing_metadata_{key}",
                    message=f"metadata_json.{key} is missing or empty",
                    **issue_context,
                ),
            )

    if not beverage.name_ko:
        issues.append(
            CatalogAuditIssue(
                severity=WARNING,
                code="missing_name_ko",
                message="active beverage is missing Korean display name",
                **issue_context,
            ),
        )
    if not beverage.name_en:
        issues.append(
            CatalogAuditIssue(
                severity=WARNING,
                code="missing_name_en",
                message="active beverage is missing English display name",
                **issue_context,
            ),
        )
    if not _has_value(metadata.get("reason_code_hints")):
        issues.append(
            CatalogAuditIssue(
                severity=WARNING,
                code="weak_reason_code_coverage",
                message="reason_code_hints is empty",
                **issue_context,
            ),
        )
    _audit_image_metadata(metadata, issue_context, issues)


def _audit_image_metadata(
    metadata: dict[str, Any],
    issue_context: dict[str, str | None],
    issues: list[CatalogAuditIssue],
) -> None:
    image_url = _optional_string(metadata.get("image_url"))
    alt_text_ko = _optional_string(metadata.get("image_alt_text_ko"))
    image = metadata.get("image")

    if image_url is None:
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code="missing_display_image",
                message="active beverage is missing metadata_json.image_url",
                **issue_context,
            ),
        )
    elif not _is_https_url(image_url):
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code="invalid_display_image_url",
                message="metadata_json.image_url must be a non-empty https URL",
                **issue_context,
            ),
        )

    if alt_text_ko is None:
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code="missing_image_alt_text_ko",
                message="active beverage is missing metadata_json.image_alt_text_ko",
                **issue_context,
            ),
        )

    if not isinstance(image, dict):
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code="missing_image_metadata",
                message="active beverage is missing metadata_json.image metadata",
                **issue_context,
            ),
        )
        return

    missing_fields = [
        field for field in REQUIRED_IMAGE_FIELDS if not _has_value(image.get(field))
    ]
    if missing_fields:
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code="missing_image_license_metadata",
                message=f"metadata_json.image is missing fields: {missing_fields}",
                **issue_context,
            ),
        )

    nested_image_url = _optional_string(image.get("image_url"))
    if nested_image_url is not None and not _is_https_url(nested_image_url):
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code="invalid_nested_image_url",
                message="metadata_json.image.image_url must be a non-empty https URL",
                **issue_context,
            ),
        )
    original_image_url = _optional_string(image.get("original_image_url"))
    if original_image_url is not None and not _is_https_url(original_image_url):
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code="invalid_original_image_url",
                message="metadata_json.image.original_image_url must be an https URL",
                **issue_context,
            ),
        )
    if image_url and nested_image_url and image_url != nested_image_url:
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code="inconsistent_image_url",
                message="metadata_json.image_url does not match image.image_url",
                **issue_context,
            ),
        )

    cache_key = _optional_string(image.get("cache_key"))
    if cache_key is not None and not _is_relative_cache_key(cache_key):
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code="invalid_image_cache_key",
                message=(
                    "metadata_json.image.cache_key must be a relative object key"
                ),
                **issue_context,
            ),
        )

    cache_policy = _optional_string(image.get("cache_policy"))
    if cache_policy and cache_policy not in ALLOWED_IMAGE_CACHE_POLICIES:
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code="invalid_image_cache_policy",
                message=f"unsupported image cache policy: {cache_policy}",
                **issue_context,
            ),
        )

    display_url_source = _optional_string(image.get("display_url_source"))
    if (
        display_url_source
        and display_url_source not in ALLOWED_IMAGE_DISPLAY_URL_SOURCES
    ):
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code="invalid_image_display_url_source",
                message=f"unsupported image display URL source: {display_url_source}",
                **issue_context,
            ),
        )

    for field in ("source_url", "license_url"):
        value = _optional_string(image.get(field))
        if value is not None and not _is_https_url(value):
            issues.append(
                CatalogAuditIssue(
                    severity=CRITICAL,
                    code=f"invalid_image_{field}",
                    message=f"metadata_json.image.{field} must be an https URL",
                    **issue_context,
                ),
            )

    policy_version = _optional_string(image.get("policy_version"))
    if policy_version and policy_version not in ALLOWED_IMAGE_POLICY_VERSIONS:
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code="invalid_image_policy_version",
                message=f"unsupported image policy version: {policy_version}",
                **issue_context,
            ),
        )

    display_policy = _optional_string(image.get("display_policy"))
    if display_policy and display_policy not in ALLOWED_IMAGE_DISPLAY_POLICIES:
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code="invalid_image_display_policy",
                message=f"unsupported image display policy: {display_policy}",
                **issue_context,
            ),
        )

    review_status = _optional_string(image.get("review_status"))
    if review_status and review_status not in ALLOWED_IMAGE_REVIEW_STATUSES:
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code="invalid_image_review_status",
                message=f"unsupported image review status: {review_status}",
                **issue_context,
            ),
        )

    if image.get("attribution_required") is True and not _has_value(
        image.get("attribution"),
    ):
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code="missing_required_image_attribution",
                message="image requires attribution but attribution is missing",
                **issue_context,
            ),
        )


def _audit_flavor_profile(
    beverage: BeverageItem,
    flavor_profiles: tuple[FlavorProfile, ...],
    issue_context: dict[str, str | None],
    issues: list[CatalogAuditIssue],
    dimension_names: set[str],
) -> None:
    if not flavor_profiles:
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code="missing_flavor_profile",
                message="active beverage has no flavor profile",
                **issue_context,
            ),
        )
        return
    if len(flavor_profiles) > 1:
        issues.append(
            CatalogAuditIssue(
                severity=WARNING,
                code="multiple_flavor_profiles",
                message="active beverage has multiple flavor profiles",
                **issue_context,
            ),
        )

    profile_json = flavor_profiles[0].profile_json or {}
    dimension_values = profile_json.get("dimension_values")
    if isinstance(dimension_values, dict):
        unknown = sorted(set(dimension_values) - dimension_names)
        missing = sorted(dimension_names - set(dimension_values))
        if unknown:
            issues.append(
                CatalogAuditIssue(
                    severity=CRITICAL,
                    code="unknown_flavor_dimensions",
                    message=f"flavor profile has unknown dimensions: {unknown}",
                    **issue_context,
                ),
            )
        if missing:
            issues.append(
                CatalogAuditIssue(
                    severity=CRITICAL,
                    code="missing_flavor_dimensions",
                    message=f"flavor profile is missing dimensions: {missing}",
                    **issue_context,
                ),
            )
    else:
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code="missing_flavor_dimension_values",
                message="flavor profile is missing profile_json.dimension_values",
                **issue_context,
            ),
        )

    if not beverage.metadata_json.get("reason_code_hints") and not profile_json.get(
        "reason_code_hints",
    ):
        issues.append(
            CatalogAuditIssue(
                severity=WARNING,
                code="missing_flavor_reason_code_hints",
                message="flavor profile and beverage metadata both lack reason hints",
                **issue_context,
            ),
        )


def _audit_vectors(
    beverage: BeverageItem,
    vectors: tuple[RecommendationVector, ...],
    issue_context: dict[str, str | None],
    issues: list[CatalogAuditIssue],
    dimension_names: set[str],
) -> None:
    if not vectors:
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code="missing_active_vector",
                message="active beverage has no recommendation vector",
                **issue_context,
            ),
        )
        return

    if len(vectors) > 1:
        issues.append(
            CatalogAuditIssue(
                severity=WARNING,
                code="multiple_recommendation_vectors",
                message="active beverage has multiple recommendation vectors",
                **issue_context,
            ),
        )

    for vector in vectors:
        if vector.owner_type != VectorOwnerType.BEVERAGE_ITEM.value:
            issues.append(
                CatalogAuditIssue(
                    severity=CRITICAL,
                    code="invalid_vector_owner_type",
                    message=f"vector owner_type is {vector.owner_type}",
                    **issue_context,
                ),
            )
        if vector.owner_id != beverage.id:
            issues.append(
                CatalogAuditIssue(
                    severity=CRITICAL,
                    code="invalid_vector_owner_id",
                    message="vector owner_id does not match beverage id",
                    **issue_context,
                ),
            )
        if len(vector.vector) != len(TASTE_V1_DIMENSIONS):
            issues.append(
                CatalogAuditIssue(
                    severity=CRITICAL,
                    code="invalid_vector_length",
                    message=(
                        f"vector length {len(vector.vector)} does not match "
                        f"{TASTE_V1_NAME} length {len(TASTE_V1_DIMENSIONS)}"
                    ),
                    **issue_context,
                ),
            )
        _audit_dimension_json(
            vector.vector_json,
            dimension_names,
            "vector_json",
            issue_context,
            issues,
        )
        _audit_dimension_json(
            vector.confidence_json,
            dimension_names,
            "confidence_json",
            issue_context,
            issues,
        )
        if not vector.source_hash:
            issues.append(
                CatalogAuditIssue(
                    severity=CRITICAL,
                    code="missing_vector_source_hash",
                    message="recommendation vector is missing source_hash",
                    **issue_context,
                ),
            )
        if not _has_value(vector.source_metadata_json):
            issues.append(
                CatalogAuditIssue(
                    severity=WARNING,
                    code="missing_vector_source_metadata",
                    message="recommendation vector is missing source metadata",
                    **issue_context,
                ),
            )


def _audit_dimension_json(
    value: dict[str, Any],
    dimension_names: set[str],
    field_name: str,
    issue_context: dict[str, str | None],
    issues: list[CatalogAuditIssue],
) -> None:
    keys = set(value or {})
    unknown = sorted(keys - dimension_names)
    missing = sorted(dimension_names - keys)
    if unknown:
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code=f"unknown_{field_name}_dimensions",
                message=f"{field_name} has unknown dimensions: {unknown}",
                **issue_context,
            ),
        )
    if missing:
        issues.append(
            CatalogAuditIssue(
                severity=CRITICAL,
                code=f"missing_{field_name}_dimensions",
                message=f"{field_name} is missing dimensions: {missing}",
                **issue_context,
            ),
        )


def _metrics(
    *,
    beverages: tuple[BeverageItem, ...],
    vectors: tuple[RecommendationVector, ...],
    flavor_profiles: tuple[FlavorProfile, ...],
    category_counts: Counter[str],
    style_counts: Counter[str],
    issues: list[CatalogAuditIssue],
) -> dict[str, Any]:
    severity_counts = Counter(issue.severity for issue in issues)
    reason_hints_count = sum(
        1
        for beverage in beverages
        if _has_value((beverage.metadata_json or {}).get("reason_code_hints"))
    )
    alias_count = sum(
        1
        for beverage in beverages
        if _has_value((beverage.metadata_json or {}).get("aliases_en"))
        or _has_value((beverage.metadata_json or {}).get("aliases_ko"))
    )
    priced_beverage_count = sum(
        1
        for beverage in beverages
        if beverage.price_min_krw is not None and beverage.price_max_krw is not None
    )
    price_observation_count = sum(
        int(
            ((beverage.metadata_json or {}).get("price_observation_summary") or {}).get(
                "observation_count",
                0,
            ),
        )
        for beverage in beverages
    )
    source_metadata_count = sum(
        1
        for vector in vectors
        if _has_value(vector.source_metadata_json)
        and _has_value(vector.source_metadata_json.get("seed_version"))
    )
    confidence_complete_count = sum(
        1
        for vector in vectors
        if _dimension_keys_are_complete(vector.confidence_json)
    )
    vector_complete_count = sum(
        1
        for vector in vectors
        if len(vector.vector) == len(TASTE_V1_DIMENSIONS)
        and _dimension_keys_are_complete(vector.vector_json)
    )
    image_url_count = sum(
        1
        for beverage in beverages
        if _optional_string((beverage.metadata_json or {}).get("image_url")) is not None
    )
    image_metadata_count = sum(
        1 for beverage in beverages if _has_image_metadata(beverage.metadata_json or {})
    )
    image_license_metadata_count = sum(
        1
        for beverage in beverages
        if _has_image_license_metadata(beverage.metadata_json or {})
    )
    image_cache_metadata_count = sum(
        1
        for beverage in beverages
        if _has_image_cache_metadata(beverage.metadata_json or {})
    )
    image_attribution_required_count = sum(
        1
        for beverage in beverages
        if _image_attribution_required(beverage.metadata_json or {})
    )
    image_kind_counts = Counter(
        image["image_kind"]
        for beverage in beverages
        if isinstance((image := (beverage.metadata_json or {}).get("image")), dict)
        and _optional_string(image.get("image_kind")) is not None
    )
    image_policy_counts = Counter(
        image["policy_version"]
        for beverage in beverages
        if isinstance((image := (beverage.metadata_json or {}).get("image")), dict)
        and _optional_string(image.get("policy_version")) is not None
    )
    return {
        "active_beverages": len(beverages),
        "priced_beverages": priced_beverage_count,
        "price_observations": price_observation_count,
        "recommendation_vectors": len(vectors),
        "flavor_profiles": len(flavor_profiles),
        "category_counts": dict(sorted(category_counts.items())),
        "style_counts": dict(sorted(style_counts.items())),
        "vector_coverage": _ratio(len(vectors), len(beverages)),
        "complete_vector_coverage": _ratio(vector_complete_count, len(beverages)),
        "flavor_profile_coverage": _ratio(len(flavor_profiles), len(beverages)),
        "style_coverage": _ratio(sum(style_counts.values()), len(beverages)),
        "confidence_coverage": _ratio(confidence_complete_count, len(beverages)),
        "source_metadata_coverage": _ratio(source_metadata_count, len(beverages)),
        "reason_code_coverage": _ratio(reason_hints_count, len(beverages)),
        "alias_coverage": _ratio(alias_count, len(beverages)),
        "image_url_coverage": _ratio(image_url_count, len(beverages)),
        "image_metadata_coverage": _ratio(image_metadata_count, len(beverages)),
        "image_license_metadata_coverage": _ratio(
            image_license_metadata_count,
            len(beverages),
        ),
        "image_cache_metadata_coverage": _ratio(
            image_cache_metadata_count,
            len(beverages),
        ),
        "image_attribution_required_count": image_attribution_required_count,
        "image_kind_counts": dict(sorted(image_kind_counts.items())),
        "image_policy_counts": dict(sorted(image_policy_counts.items())),
        "issue_counts": {
            CRITICAL: severity_counts.get(CRITICAL, 0),
            WARNING: severity_counts.get(WARNING, 0),
            INFO: severity_counts.get(INFO, 0),
        },
    }


def _group_by_owner(items) -> dict[uuid.UUID, tuple[Any, ...]]:
    grouped: dict[uuid.UUID, list[Any]] = {}
    for item in items:
        grouped.setdefault(item.owner_id, []).append(item)
    return {
        owner_id: tuple(sorted(values, key=lambda item: str(item.id)))
        for owner_id, values in grouped.items()
    }


def _beverage_sort_key(beverage: BeverageItem) -> tuple[str, str, str]:
    metadata = beverage.metadata_json or {}
    return (
        beverage.category,
        _optional_string(metadata.get("catalog_key")) or "",
        str(beverage.id),
    )


def _issue_sort_key(issue: CatalogAuditIssue) -> tuple[int, str, str, str]:
    severity_order = {CRITICAL: 0, WARNING: 1, INFO: 2}
    return (
        severity_order.get(issue.severity, 99),
        issue.catalog_key or "",
        issue.beverage_id or "",
        issue.code,
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _has_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value)
    if isinstance(value, list | tuple | dict | set):
        return bool(value)
    return True


def _is_https_url(value: str) -> bool:
    return value.startswith("https://") and len(value) > len("https://")


def _has_image_metadata(metadata: dict[str, Any]) -> bool:
    image = metadata.get("image")
    return (
        isinstance(image, dict)
        and _optional_string(image.get("image_url")) is not None
    )


def _has_image_license_metadata(metadata: dict[str, Any]) -> bool:
    image = metadata.get("image")
    if not isinstance(image, dict):
        return False
    return all(_has_value(image.get(field)) for field in REQUIRED_IMAGE_FIELDS)


def _has_image_cache_metadata(metadata: dict[str, Any]) -> bool:
    image = metadata.get("image")
    if not isinstance(image, dict):
        return False
    return (
        _optional_string(image.get("original_image_url")) is not None
        and _optional_string(image.get("cache_key")) is not None
        and _optional_string(image.get("cache_policy")) is not None
        and _optional_string(image.get("display_url_source")) is not None
    )


def _image_attribution_required(metadata: dict[str, Any]) -> bool:
    image = metadata.get("image")
    return isinstance(image, dict) and image.get("attribution_required") is True


def _is_relative_cache_key(value: str) -> bool:
    return (
        not value.startswith(("/", "http://", "https://"))
        and ".." not in value.split("/")
        and bool(value.strip())
    )


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 6)


def _dimension_keys_are_complete(value: dict[str, Any]) -> bool:
    return set(value or {}) == {dimension.name for dimension in TASTE_V1_DIMENSIONS}
