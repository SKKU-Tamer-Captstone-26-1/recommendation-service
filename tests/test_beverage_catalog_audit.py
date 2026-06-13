import uuid
from pathlib import Path

from app.domain.vector_schema import TASTE_V1_DIMENSIONS
from app.models.catalog import BeverageItem, FlavorProfile
from app.models.enums import FlavorProfileOwnerType, VectorOwnerType
from app.models.vector import RecommendationVector
from app.services.beverage_catalog_audit import (
    CRITICAL,
    audit_catalog_rows,
    audit_seed_records,
)
from app.services.beverage_import import (
    build_canonical_seed_records,
    load_candidate_artifacts,
)


def test_current_seed_subset_passes_critical_catalog_audit() -> None:
    records = build_canonical_seed_records(
        artifacts=load_candidate_artifacts(Path("data/beverage")),
        vector_schema_version_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
    )

    report = audit_seed_records(records)

    assert report.critical_count == 0
    assert report.metrics["active_beverages"] == 60
    assert report.metrics["recommendation_vectors"] == 60
    assert report.metrics["flavor_profiles"] == 60
    assert report.metrics["complete_vector_coverage"] == 1.0
    assert report.metrics["confidence_coverage"] == 1.0
    assert report.metrics["source_metadata_coverage"] == 1.0
    assert report.metrics["reason_code_coverage"] >= 0.95
    assert report.metrics["alias_coverage"] >= 0.95
    assert report.metrics["style_coverage"] == 1.0
    assert report.metrics["image_url_coverage"] == 1.0
    assert report.metrics["image_metadata_coverage"] == 1.0
    assert report.metrics["image_license_metadata_coverage"] == 1.0
    assert report.metrics["image_cache_metadata_coverage"] == 1.0
    assert report.metrics["image_kind_counts"] == {
        "category_representative": 48,
        "licensed_cocktail_representative": 5,
        "licensed_product_representative": 7,
    }
    assert report.metrics["image_policy_counts"] == {"beverage_image_v1": 60}
    assert report.metrics["category_counts"] == {
        "beer": 5,
        "brandy_cognac": 5,
        "cocktail": 5,
        "gin": 5,
        "liqueur": 5,
        "rum": 5,
        "sake_shochu": 5,
        "tequila_mezcal": 5,
        "traditional_korean_alcohol": 5,
        "vodka": 5,
        "whiskey": 5,
        "wine": 5,
    }


def test_catalog_audit_detects_missing_vector_and_metadata() -> None:
    beverage = _beverage(metadata={"style": "bourbon"})
    flavor_profile = _flavor_profile(beverage.id)

    report = audit_catalog_rows(
        beverages=(beverage,),
        vectors=(),
        flavor_profiles=(flavor_profile,),
        source="test",
    )

    codes = {issue.code for issue in report.issues if issue.severity == CRITICAL}
    assert "missing_active_vector" in codes
    assert "missing_metadata_catalog_key" in codes
    assert "missing_metadata_source_version" in codes


def test_catalog_audit_detects_bad_vector_dimensions() -> None:
    beverage = _beverage()
    flavor_profile = _flavor_profile(beverage.id)
    vector = _vector(
        beverage.id,
        vector=[0.1, 0.2],
        vector_json={"sweet": 0.1, "invalid": 0.2},
        confidence_json={"sweet": 0.8},
    )

    report = audit_catalog_rows(
        beverages=(beverage,),
        vectors=(vector,),
        flavor_profiles=(flavor_profile,),
        source="test",
    )

    codes = {issue.code for issue in report.issues if issue.severity == CRITICAL}
    assert "invalid_vector_length" in codes
    assert "unknown_vector_json_dimensions" in codes
    assert "missing_confidence_json_dimensions" in codes


def test_catalog_audit_detects_missing_display_image_metadata() -> None:
    metadata = _base_metadata()
    for key in (
        "image",
        "image_url",
        "image_alt_text_ko",
        "image_source_url",
        "image_license",
        "image_attribution",
        "image_display_policy",
        "image_kind",
        "image_review_status",
        "image_policy_version",
    ):
        metadata.pop(key, None)
    beverage = _beverage(metadata=metadata)

    report = audit_catalog_rows(
        beverages=(beverage,),
        vectors=(_vector(beverage.id),),
        flavor_profiles=(_flavor_profile(beverage.id),),
        source="test",
    )

    codes = {issue.code for issue in report.issues if issue.severity == CRITICAL}
    assert "missing_display_image" in codes
    assert "missing_image_alt_text_ko" in codes
    assert "missing_image_metadata" in codes


def test_catalog_audit_detects_duplicate_catalog_keys() -> None:
    first = _beverage(catalog_key="whiskey.duplicate")
    second = _beverage(catalog_key="whiskey.duplicate")

    report = audit_catalog_rows(
        beverages=(first, second),
        vectors=(_vector(first.id), _vector(second.id)),
        flavor_profiles=(_flavor_profile(first.id), _flavor_profile(second.id)),
        source="test",
    )

    assert any(issue.code == "duplicate_catalog_key" for issue in report.issues)
    assert report.critical_count == 1


def _beverage(
    *,
    catalog_key: str = "whiskey.test_bourbon",
    metadata: dict[str, object] | None = None,
) -> BeverageItem:
    resolved_metadata = metadata or _base_metadata(catalog_key=catalog_key)
    return BeverageItem(
        id=uuid.uuid4(),
        category="whiskey",
        name_ko="테스트 버번",
        name_en="Test Bourbon",
        active=True,
        metadata_json=resolved_metadata,
    )


def _base_metadata(
    *,
    catalog_key: str = "whiskey.test_bourbon",
) -> dict[str, object]:
    image = {
        "policy_version": "beverage_image_v1",
        "image_candidate_id": "bev_image_whiskey_category_representative_001",
        "image_kind": "category_representative",
        "image_url": (
            "https://commons.wikimedia.org/wiki/Special:FilePath/"
            "Glass_of_whisky.jpg"
        ),
        "original_image_url": (
            "https://commons.wikimedia.org/wiki/Special:FilePath/"
            "Glass_of_whisky.jpg"
        ),
        "cache_key": (
            "beverage-images/v1/"
            "bev_image_whiskey_category_representative_001.jpg"
        ),
        "cache_policy": "operator_managed_image_cache_v1",
        "display_url_source": "licensed_source_url",
        "alt_text_ko": "위스키 잔 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Glass_of_whisky.jpg",
        "source_type": "wikimedia_commons",
        "license": "Public Domain",
        "license_url": "https://commons.wikimedia.org/wiki/File:Glass_of_whisky.jpg",
        "attribution": "Chris huh / Wikimedia Commons",
        "attribution_required": False,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
    }
    return {
        "catalog_key": catalog_key,
        "style": "bourbon",
        "source_type": "operator_reviewed_candidate_seed",
        "source_version": "canonical_beverage_seed_v1",
        "curation_status": "approved_mvp_seed",
        "reason_code_hints": ["MATCHES_VANILLA_CARAMEL"],
        "aliases_en": ["Test Bourbon"],
        "aliases_ko": ["테스트 버번"],
        "serving_context": ["neat"],
        "image": image,
        "image_url": image["image_url"],
        "image_alt_text_ko": image["alt_text_ko"],
        "image_source_url": image["source_url"],
        "image_license": image["license"],
        "image_attribution": image["attribution"],
        "image_display_policy": image["display_policy"],
        "image_kind": image["image_kind"],
        "image_review_status": image["review_status"],
        "image_policy_version": image["policy_version"],
    }


def _flavor_profile(beverage_id: uuid.UUID) -> FlavorProfile:
    dimension_values = {dimension.name: 0.2 for dimension in TASTE_V1_DIMENSIONS}
    return FlavorProfile(
        id=uuid.uuid4(),
        owner_type=FlavorProfileOwnerType.BEVERAGE_ITEM.value,
        owner_id=beverage_id,
        flavor_tags=["whiskey", "bourbon"],
        profile_json={
            "vector_schema": "taste_v1",
            "dimension_values": dimension_values,
            "dimension_confidence": {
                dimension.name: 0.7 for dimension in TASTE_V1_DIMENSIONS
            },
            "reason_code_hints": ["MATCHES_VANILLA_CARAMEL"],
        },
        curation_confidence=0.8,
        source="test",
    )


def _vector(
    beverage_id: uuid.UUID,
    *,
    vector: list[float] | None = None,
    vector_json: dict[str, float] | None = None,
    confidence_json: dict[str, float] | None = None,
) -> RecommendationVector:
    values = vector or [0.2] * len(TASTE_V1_DIMENSIONS)
    named_values = vector_json or {
        dimension.name: values[index]
        for index, dimension in enumerate(TASTE_V1_DIMENSIONS)
    }
    confidence = confidence_json or {
        dimension.name: 0.7 for dimension in TASTE_V1_DIMENSIONS
    }
    return RecommendationVector(
        id=uuid.uuid4(),
        owner_type=VectorOwnerType.BEVERAGE_ITEM.value,
        owner_id=beverage_id,
        vector_schema_version_id=uuid.uuid4(),
        vector=values,
        vector_json=named_values,
        confidence_json=confidence,
        source_hash="source_hash",
        source_metadata_json={"seed_version": "test"},
    )
