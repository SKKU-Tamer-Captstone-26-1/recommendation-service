import csv
import json
from pathlib import Path

from app.tools.beverage_candidate_dry_run import (
    EXTENDED_BEVERAGE_DIMENSIONS,
    TASTE_V1_DIMENSIONS,
    main,
    run_dry_run,
)


def test_dry_run_accepts_valid_candidate_set(tmp_path: Path) -> None:
    data_dir = _write_valid_data_dir(tmp_path)
    report_path = tmp_path / "report.md"

    result = run_dry_run(data_dir, report_path=report_path)

    assert result.exit_code == 0
    assert result.accepted_rows == 6
    assert result.warning_rows == 0
    assert result.rejected_rows == 0
    assert report_path.exists()
    assert "## Accepted Rows" in report_path.read_text()


def test_dry_run_warns_without_nonzero_exit(tmp_path: Path) -> None:
    data_dir = _write_valid_data_dir(tmp_path)
    catalog_path = data_dir / "catalog_candidates.jsonl"
    catalog_row = _read_jsonl(catalog_path)[0]
    catalog_row["candidate_status"] = "collected"
    _write_jsonl(catalog_path, [catalog_row])

    code = main(["--data-dir", str(data_dir)])

    assert code == 0
    result = run_dry_run(data_dir)
    assert result.warning_rows == 1
    assert result.rejected_rows == 0


def test_dry_run_rejects_invalid_rows_and_cli_returns_nonzero(
    tmp_path: Path,
) -> None:
    data_dir = _write_valid_data_dir(tmp_path)
    catalog_path = data_dir / "catalog_candidates.jsonl"
    price_path = data_dir / "price_observation_candidates.jsonl"
    flavor_path = data_dir / "flavor_profile_candidates.jsonl"
    knowledge_path = data_dir / "knowledge_candidates.jsonl"
    report_path = tmp_path / "rejected.md"

    catalog_row = _read_jsonl(catalog_path)[0]
    catalog_row["category"] = "bad_category"
    _write_jsonl(catalog_path, [catalog_row])

    price_row = _read_jsonl(price_path)[0]
    price_row["currency"] = "USD"
    price_row["market_region"] = "US"
    price_row["price_type"] = "retail_bottle_point_in_time"
    _write_jsonl(price_path, [price_row])
    _write_jsonl(flavor_path, [])
    _write_jsonl(knowledge_path, [])

    code = main(
        [
            "--data-dir",
            str(data_dir),
            "--report",
            str(report_path),
        ],
    )

    assert code == 1
    report = report_path.read_text()
    assert "invalid_category" in report
    assert "invalid_price_currency" in report
    assert "missing_package_size" in report
    assert "missing_flavor_candidate" in report
    assert "missing_knowledge_candidate" in report


def _write_valid_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "beverage"
    data_dir.mkdir()
    _write_source_registry(
        data_dir / "source_registry.csv",
        [
            {
                "source_id": "src_product",
                "title": "Product source",
                "url": "https://example.com/product",
                "source_type": "official_producer",
                "owner_or_publisher": "Example",
                "usage_lanes": "catalog;flavor;knowledge",
                "license_or_usage_note": "source reference only",
                "source_confidence": "high",
                "retrieved_at": "2026-05-23",
                "notes": "test source",
            },
            {
                "source_id": "src_price",
                "title": "Price source",
                "url": "https://example.com/price",
                "source_type": "retailer",
                "owner_or_publisher": "Example",
                "usage_lanes": "price",
                "license_or_usage_note": "point-in-time price only",
                "source_confidence": "medium",
                "retrieved_at": "2026-05-23",
                "notes": "test source",
            },
        ],
    )
    _write_jsonl(data_dir / "catalog_candidates.jsonl", [_catalog_row()])
    _write_jsonl(data_dir / "flavor_profile_candidates.jsonl", [_flavor_row()])
    _write_jsonl(data_dir / "knowledge_candidates.jsonl", [_knowledge_row()])
    _write_jsonl(data_dir / "price_observation_candidates.jsonl", [_price_row()])
    return data_dir


def _catalog_row() -> dict[str, object]:
    return {
        "beverage_candidate_id": "bev_cand_whiskey_test_bourbon",
        "canonical_name_en": "Test Bourbon",
        "display_name_ko": "테스트 버번",
        "aliases_en": [],
        "aliases_ko": [],
        "normalized_name": "test bourbon",
        "beverage_slug": "test_bourbon",
        "category": "whiskey",
        "style": "bourbon",
        "candidate_status": "needs_review",
        "source_urls": ["https://example.com/product"],
        "source_confidence": "high",
        "collected_at": "2026-05-23T12:00:00+09:00",
        "abv": 45.0,
        "beginner_friendly_score": 0.6,
    }


def _flavor_row() -> dict[str, object]:
    return {
        "flavor_candidate_id": "flavor_cand_whiskey_test_bourbon",
        "beverage_candidate_id": "bev_cand_whiskey_test_bourbon",
        "vector_schema": "beverage_vector_v1_candidate",
        "taste_v1_dimension_values": {
            dimension: 0.2 for dimension in TASTE_V1_DIMENSIONS
        },
        "extended_dimension_values": {
            dimension: 0.2 for dimension in EXTENDED_BEVERAGE_DIMENSIONS
        },
        "flavor_confidence_overall": 0.7,
        "dimension_confidence_json": {"all_other_dimensions": 0.5},
        "evidence_summary": "test evidence",
        "source_urls": ["https://example.com/product"],
        "candidate_status": "needs_review",
    }


def _knowledge_row() -> dict[str, object]:
    return {
        "knowledge_candidate_id": "know_cand_whiskey_test_bourbon",
        "beverage_candidate_id": "bev_cand_whiskey_test_bourbon",
        "title": "Test Bourbon overview",
        "language": "ko",
        "document_type": "beverage_profile",
        "summary_text": "테스트 후보입니다.",
        "chunk_text": "테스트 설명 후보입니다.",
        "source_url": "https://example.com/product",
        "source_title": "Product source",
        "source_type": "official_producer",
        "license_or_usage_note": "paraphrased",
        "retrieved_at": "2026-05-23",
        "source_confidence": "high",
        "candidate_status": "needs_review",
    }


def _price_row() -> dict[str, object]:
    return {
        "price_observation_id": "price_obs_whiskey_test_bourbon_2026_05_23",
        "beverage_candidate_id": "bev_cand_whiskey_test_bourbon",
        "canonical_name_en": "Test Bourbon",
        "market_region": "KR",
        "currency": "KRW",
        "price_min": 45000,
        "price_max": 45000,
        "price_value": 45000,
        "price_type": "kr_retail_pickup_bottle_700ml_point_in_time",
        "source_url": "https://example.com/price",
        "source_type": "retailer",
        "observed_at": "2026-05-23",
        "retrieved_at": "2026-05-23",
        "confidence": 0.7,
        "notes": "point-in-time test price",
    }


def _write_source_registry(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
