import uuid
from pathlib import Path

from app.domain.vector_schema import TASTE_V1_DIMENSION_COUNT, TASTE_V1_DIMENSIONS
from app.models.enums import VectorOwnerType
from app.services.beverage_import import (
    MVP_SEED_CANDIDATE_IDS,
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
