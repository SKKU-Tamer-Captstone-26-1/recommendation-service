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

    assert len(records) == 24
    assert len(MVP_SEED_CANDIDATE_IDS) == 24
    assert {record.beverage.category for record in records} == {
        "beer",
        "brandy_cognac",
        "cocktail",
        "gin",
        "liqueur",
        "rum",
        "sake_shochu",
        "tequila_mezcal",
        "traditional_korean_alcohol",
        "vodka",
        "whiskey",
        "wine",
    }
    assert all(record.beverage.active for record in records)
    assert all(record.beverage.price_min_krw is None for record in records)
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
