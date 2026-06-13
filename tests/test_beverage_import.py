import json
import uuid
from pathlib import Path

import pytest

from app.domain.vector_schema import TASTE_V1_DIMENSION_COUNT, TASTE_V1_DIMENSIONS
from app.models.enums import VectorOwnerType
from app.services.beverage_import import (
    MVP_SEED_CANDIDATE_IDS,
    BeverageImportError,
    build_canonical_seed_records,
    load_candidate_artifacts,
)


def test_canonical_seed_subset_builds_reviewed_records() -> None:
    artifacts = load_candidate_artifacts(Path("data/beverage"))
    schema_id = uuid.UUID("11111111-1111-4111-8111-111111111111")

    records = build_canonical_seed_records(
        artifacts=artifacts,
        vector_schema_version_id=schema_id,
    )

    assert len(records) == 60
    assert len(MVP_SEED_CANDIDATE_IDS) == 60
    category_counts = {}
    for record in records:
        category_counts[record.beverage.category] = (
            category_counts.get(record.beverage.category, 0) + 1
        )
    assert category_counts == {
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
    assert all(record.beverage.active for record in records)
    priced_records = [
        record for record in records if record.beverage.price_min_krw is not None
    ]
    assert len(priced_records) == 49
    assert all(
        record.beverage.price_max_krw is not None for record in priced_records
    )
    assert all(record.beverage.metadata_json["aliases_en"] for record in records)
    assert all(record.beverage.metadata_json["aliases_ko"] for record in records)
    assert all(record.beverage.metadata_json["image_url"] for record in records)
    assert all(
        record.beverage.metadata_json["image"]["policy_version"]
        == "beverage_image_v1"
        for record in records
    )
    assert all(
        record.beverage.metadata_json["image"]["original_image_url"]
        for record in records
    )
    assert all(
        record.beverage.metadata_json["image"]["cache_key"] for record in records
    )
    assert all(
        record.beverage.metadata_json["image"]["cache_policy"]
        == "operator_managed_image_cache_v1"
        for record in records
    )
    image_kind_counts = {}
    for record in records:
        image_kind = record.beverage.metadata_json["image_kind"]
        image_kind_counts[image_kind] = image_kind_counts.get(image_kind, 0) + 1
    assert image_kind_counts == {
        "category_representative": 48,
        "licensed_cocktail_representative": 5,
        "licensed_product_representative": 7,
    }
    assert all(
        record.beverage.metadata_json["reason_code_hints"] for record in records
    )
    assert all(
        record.vector.owner_type == VectorOwnerType.BEVERAGE_ITEM.value
        for record in records
    )
    assert all(
        len(record.vector.vector) == TASTE_V1_DIMENSION_COUNT
        for record in records
    )
    assert all(
        set(record.vector.vector_json)
        == {dimension.name for dimension in TASTE_V1_DIMENSIONS}
        for record in records
    )

    buffalo_trace = next(
        record
        for record in records
        if record.beverage.metadata_json["catalog_key"]
        == "whiskey.buffalo_trace_bourbon"
    )
    assert buffalo_trace.beverage.price_min_krw == 39000
    assert buffalo_trace.beverage.price_max_krw == 39000
    assert buffalo_trace.beverage.metadata_json["image_url"] == (
        "https://commons.wikimedia.org/wiki/Special:FilePath/"
        "Buffalo_Trace_bourbon_whiskey.jpg"
    )
    assert buffalo_trace.beverage.metadata_json["image"]["original_image_url"] == (
        "https://commons.wikimedia.org/wiki/Special:FilePath/"
        "Buffalo_Trace_bourbon_whiskey.jpg"
    )
    assert buffalo_trace.beverage.metadata_json["image"]["cache_key"] == (
        "beverage-images/v1/"
        "bev_image_whiskey_buffalo_trace_bourbon_product_001.jpg"
    )
    assert buffalo_trace.beverage.metadata_json["image"][
        "display_url_source"
    ] == "licensed_source_url"
    assert buffalo_trace.beverage.metadata_json["image_alt_text_ko"] == (
        "버팔로 트레이스 버번 병 대표 이미지"
    )
    assert buffalo_trace.beverage.metadata_json["image_kind"] == (
        "licensed_product_representative"
    )
    assert buffalo_trace.beverage.metadata_json["price_policy"] == (
        "verified_krw_observations_not_live_truth"
    )
    assert buffalo_trace.beverage.metadata_json["price_observation_summary"] == {
        "confidence_max": 0.62,
        "confidence_min": 0.62,
        "currency": "KRW",
        "market_region": "KR",
        "observation_count": 1,
        "observed_at_max": "2026-05-22",
        "observed_at_min": "2026-05-22",
        "policy": "verified_krw_observations_not_live_truth",
        "price_max_krw": 39000,
        "price_min_krw": 39000,
        "retrieved_at_max": "2026-05-22",
    }
    assert buffalo_trace.beverage.metadata_json["price_observations"][0][
        "price_observation_id"
    ] == "price_obs_kr_whiskey_buffalo_trace_dailyshot_2026_05_22"


def test_canonical_seed_uses_cdn_display_urls_when_configured() -> None:
    artifacts = load_candidate_artifacts(Path("data/beverage"))
    schema_id = uuid.UUID("11111111-1111-4111-8111-111111111111")

    records = build_canonical_seed_records(
        artifacts=artifacts,
        vector_schema_version_id=schema_id,
        image_cdn_base_url="https://images.example.test/ontheblock",
    )

    buffalo_trace = next(
        record
        for record in records
        if record.beverage.metadata_json["catalog_key"]
        == "whiskey.buffalo_trace_bourbon"
    )
    expected_display_url = (
        "https://images.example.test/ontheblock/beverage-images/v1/"
        "bev_image_whiskey_buffalo_trace_bourbon_product_001.jpg"
    )
    assert buffalo_trace.beverage.metadata_json["image_url"] == expected_display_url
    assert buffalo_trace.beverage.metadata_json["image"]["image_url"] == (
        expected_display_url
    )
    assert buffalo_trace.beverage.metadata_json["image"]["original_image_url"] == (
        "https://commons.wikimedia.org/wiki/Special:FilePath/"
        "Buffalo_Trace_bourbon_whiskey.jpg"
    )
    assert buffalo_trace.beverage.metadata_json["image"][
        "display_url_source"
    ] == "operator_managed_cache"


def test_canonical_seed_rejects_non_https_image_cdn_base_url() -> None:
    artifacts = load_candidate_artifacts(Path("data/beverage"))
    schema_id = uuid.UUID("11111111-1111-4111-8111-111111111111")

    with pytest.raises(BeverageImportError, match="image CDN base URL"):
        build_canonical_seed_records(
            artifacts=artifacts,
            vector_schema_version_id=schema_id,
            image_cdn_base_url="http://images.example.test/ontheblock",
        )


def test_canonical_seed_ids_and_hashes_are_deterministic() -> None:
    artifacts = load_candidate_artifacts(Path("data/beverage"))
    schema_id = uuid.UUID("11111111-1111-4111-8111-111111111111")

    first = build_canonical_seed_records(
        artifacts=artifacts,
        vector_schema_version_id=schema_id,
    )
    second = build_canonical_seed_records(
        artifacts=artifacts,
        vector_schema_version_id=schema_id,
    )

    assert [record.beverage.id for record in first] == [
        record.beverage.id for record in second
    ]
    assert [record.vector.source_hash for record in first] == [
        record.vector.source_hash for record in second
    ]


def test_image_candidate_policy_rejects_unapproved_source_type(
    tmp_path: Path,
) -> None:
    _write_minimal_artifacts(
        tmp_path,
        image_rows=(
            _valid_image_row(
                source_type="random_search_thumbnail",
            ),
        ),
    )

    with pytest.raises(BeverageImportError, match="unsupported source_type"):
        load_candidate_artifacts(tmp_path)


def test_image_candidate_policy_rejects_unknown_direct_beverage(
    tmp_path: Path,
) -> None:
    _write_minimal_artifacts(
        tmp_path,
        image_rows=(
            _valid_image_row(
                image_candidate_id="bev_image_unknown_product_001",
                image_kind="licensed_product_representative",
                beverage_candidate_id="bev_cand_missing",
            ),
        ),
    )

    with pytest.raises(BeverageImportError, match="references unknown"):
        load_candidate_artifacts(tmp_path)


def test_image_candidate_policy_rejects_direct_category_mismatch(
    tmp_path: Path,
) -> None:
    candidate_id = "bev_cand_fixture_beer"
    _write_minimal_artifacts(
        tmp_path,
        catalog_rows=(
            {
                "beverage_candidate_id": candidate_id,
                "category": "beer",
            },
        ),
        image_rows=(
            _valid_image_row(
                image_candidate_id="bev_image_fixture_mismatch_001",
                image_kind="licensed_product_representative",
                beverage_candidate_id=candidate_id,
                category="whiskey",
            ),
        ),
    )

    with pytest.raises(BeverageImportError, match="category does not match"):
        load_candidate_artifacts(tmp_path)


def test_image_candidate_policy_requires_https_urls(tmp_path: Path) -> None:
    _write_minimal_artifacts(
        tmp_path,
        image_rows=(
            _valid_image_row(
                image_url="http://example.test/image.jpg",
            ),
        ),
    )

    with pytest.raises(BeverageImportError, match="image_url must be https URL"):
        load_candidate_artifacts(tmp_path)


def _write_minimal_artifacts(
    data_dir: Path,
    *,
    image_rows: tuple[dict[str, object], ...],
    catalog_rows: tuple[dict[str, object], ...] = (),
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "run_manifest.json").write_text("{}", encoding="utf-8")
    _write_jsonl(data_dir / "catalog_candidates.jsonl", catalog_rows)
    _write_jsonl(data_dir / "flavor_profile_candidates.jsonl", ())
    _write_jsonl(data_dir / "knowledge_candidates.jsonl", ())
    _write_jsonl(data_dir / "price_observation_candidates.jsonl", ())
    _write_jsonl(data_dir / "image_candidates.jsonl", image_rows)
    (data_dir / "source_registry.csv").write_text("source_id,url\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: tuple[dict[str, object], ...]) -> None:
    path.write_text(
        "".join(f"{json.dumps(row, ensure_ascii=False)}\n" for row in rows),
        encoding="utf-8",
    )


def _valid_image_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "image_candidate_id": "bev_image_whiskey_category_representative_fixture",
        "category": "whiskey",
        "image_kind": "category_representative",
        "image_url": (
            "https://commons.wikimedia.org/wiki/Special:FilePath/"
            "Glass_of_whisky.jpg"
        ),
        "source_url": "https://commons.wikimedia.org/wiki/File:Glass_of_whisky.jpg",
        "source_type": "wikimedia_commons",
        "license": "Public Domain",
        "license_url": "https://commons.wikimedia.org/wiki/File:Glass_of_whisky.jpg",
        "attribution": "Chris huh / Wikimedia Commons",
        "attribution_required": False,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "alt_text_ko": "위스키 잔 대표 이미지",
        "notes": "Fixture image row.",
    }
    row.update(overrides)
    return row
