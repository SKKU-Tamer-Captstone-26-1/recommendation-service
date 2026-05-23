"""Dry-run validator for beverage candidate artifacts.

The command reads local candidate files and writes a review report. It does not
open a database connection or mutate canonical catalog tables.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

CATALOG_FILE = "catalog_candidates.jsonl"
FLAVOR_FILE = "flavor_profile_candidates.jsonl"
KNOWLEDGE_FILE = "knowledge_candidates.jsonl"
PRICE_FILE = "price_observation_candidates.jsonl"
SOURCE_REGISTRY_FILE = "source_registry.csv"

ALLOWED_CATEGORIES = {
    "whiskey",
    "wine",
    "beer",
    "cocktail",
    "traditional_korean_alcohol",
    "sake_shochu",
    "gin",
    "rum",
    "tequila_mezcal",
    "vodka",
    "brandy_cognac",
    "liqueur",
}

TASTE_V1_DIMENSIONS = {
    "sweet",
    "fruity",
    "dried_fruit",
    "woody",
    "smoky",
    "nutty",
    "floral",
    "spicy",
    "herbal",
    "body",
    "acidity",
    "carbonation",
    "alcohol_intensity",
    "bitterness",
    "tannin",
    "roasted",
}

EXTENDED_BEVERAGE_DIMENSIONS = {
    "citrus",
    "tropical_fruit",
    "red_fruit",
    "vanilla",
    "caramel",
    "earthy",
    "mineral",
    "savory",
    "salinity",
    "peat",
    "oak",
    "creaminess",
    "finish_length",
    "complexity",
    "beginner_friendly",
    "serving_versatility",
}

ALLOWED_SOURCE_TYPES = {
    "official_producer",
    "official_importer_or_distributor",
    "official_institution_or_association",
    "public_data",
    "retailer",
    "blog_review",
    "community_review",
}

ALLOWED_CONFIDENCE_VALUES = {
    "high",
    "medium_high",
    "medium",
    "low_medium",
    "low",
}

CATALOG_REQUIRED_FIELDS = {
    "beverage_candidate_id",
    "canonical_name_en",
    "display_name_ko",
    "normalized_name",
    "beverage_slug",
    "category",
    "style",
    "candidate_status",
    "source_urls",
    "source_confidence",
    "collected_at",
}

FLAVOR_REQUIRED_FIELDS = {
    "flavor_candidate_id",
    "beverage_candidate_id",
    "vector_schema",
    "taste_v1_dimension_values",
    "extended_dimension_values",
    "flavor_confidence_overall",
    "dimension_confidence_json",
    "evidence_summary",
    "source_urls",
    "candidate_status",
}

KNOWLEDGE_REQUIRED_FIELDS = {
    "knowledge_candidate_id",
    "beverage_candidate_id",
    "title",
    "language",
    "document_type",
    "summary_text",
    "chunk_text",
    "source_url",
    "source_title",
    "source_type",
    "license_or_usage_note",
    "retrieved_at",
    "source_confidence",
    "candidate_status",
}

PRICE_REQUIRED_FIELDS = {
    "price_observation_id",
    "beverage_candidate_id",
    "canonical_name_en",
    "market_region",
    "currency",
    "price_min",
    "price_max",
    "price_value",
    "price_type",
    "source_url",
    "source_type",
    "observed_at",
    "retrieved_at",
    "confidence",
    "notes",
}

SOURCE_REGISTRY_REQUIRED_FIELDS = {
    "source_id",
    "title",
    "url",
    "source_type",
    "usage_lanes",
    "source_confidence",
    "retrieved_at",
}

SIZE_PATTERN = re.compile(r"(\d+\s*x\s*)?\d+\s*ml", re.IGNORECASE)


class Severity(StrEnum):
    WARNING = "warning"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ValidationIssue:
    severity: Severity
    code: str
    message: str


@dataclass
class RowResult:
    file_name: str
    line_number: int
    row_id: str
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def status(self) -> str:
        if any(issue.severity == Severity.REJECTED for issue in self.issues):
            return "rejected"
        if self.issues:
            return "warning"
        return "accepted"

    @property
    def messages(self) -> str:
        if not self.issues:
            return ""
        return "; ".join(f"{issue.code}: {issue.message}" for issue in self.issues)


@dataclass(frozen=True)
class SourceRegistry:
    urls: set[str]
    source_ids: set[str]
    source_types_by_url: dict[str, str]
    rows: list[dict[str, str]]


@dataclass
class DryRunResult:
    rows: list[RowResult]
    candidate_counts: dict[str, int]
    report_path: Path | None = None

    @property
    def accepted_rows(self) -> int:
        return sum(row.status == "accepted" for row in self.rows)

    @property
    def warning_rows(self) -> int:
        return sum(row.status == "warning" for row in self.rows)

    @property
    def rejected_rows(self) -> int:
        return sum(row.status == "rejected" for row in self.rows)

    @property
    def exit_code(self) -> int:
        return 1 if self.rejected_rows else 0


def run_dry_run(
    data_dir: Path,
    report_path: Path | None = None,
    price_currency: str = "KRW",
) -> DryRunResult:
    data_dir = data_dir.resolve()
    rows: list[RowResult] = []
    candidate_counts: dict[str, int] = {}

    registry, registry_results = _load_source_registry(data_dir / SOURCE_REGISTRY_FILE)
    rows.extend(registry_results)

    catalog_rows, catalog_results = _load_jsonl(
        data_dir / CATALOG_FILE,
        "beverage_candidate_id",
    )
    flavor_rows, flavor_results = _load_jsonl(
        data_dir / FLAVOR_FILE,
        "flavor_candidate_id",
    )
    knowledge_rows, knowledge_results = _load_jsonl(
        data_dir / KNOWLEDGE_FILE,
        "knowledge_candidate_id",
    )
    price_rows, price_results = _load_jsonl(
        data_dir / PRICE_FILE,
        "price_observation_id",
    )

    rows.extend(catalog_results)
    rows.extend(flavor_results)
    rows.extend(knowledge_results)
    rows.extend(price_results)

    candidate_counts.update(
        {
            CATALOG_FILE: len(catalog_rows),
            FLAVOR_FILE: len(flavor_rows),
            KNOWLEDGE_FILE: len(knowledge_rows),
            PRICE_FILE: len(price_rows),
            SOURCE_REGISTRY_FILE: len(registry.rows),
        }
    )

    catalog_ids = {
        row["beverage_candidate_id"]
        for row in catalog_rows
        if isinstance(row.get("beverage_candidate_id"), str)
    }
    flavor_ids = {
        row["beverage_candidate_id"]
        for row in flavor_rows
        if isinstance(row.get("beverage_candidate_id"), str)
    }
    knowledge_ids = {
        row["beverage_candidate_id"]
        for row in knowledge_rows
        if isinstance(row.get("beverage_candidate_id"), str)
    }

    _validate_catalog_rows(
        catalog_rows, _valid_loaded_results(catalog_results), registry
    )
    _validate_flavor_rows(flavor_rows, _valid_loaded_results(flavor_results), registry)
    _validate_knowledge_rows(
        knowledge_rows,
        _valid_loaded_results(knowledge_results),
        registry,
    )
    _validate_price_rows(
        price_rows,
        _valid_loaded_results(price_results),
        registry,
        catalog_ids,
        price_currency,
    )
    _validate_catalog_links(catalog_ids, flavor_ids, knowledge_ids, rows)
    _validate_duplicates(catalog_rows, flavor_rows, knowledge_rows, price_rows, rows)

    result = DryRunResult(rows=rows, candidate_counts=candidate_counts)
    if report_path is not None:
        resolved_report_path = report_path.resolve()
        resolved_report_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_report_path.write_text(
            _render_report(result, data_dir), encoding="utf-8"
        )
        result.report_path = resolved_report_path
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run beverage candidate validation without DB writes.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/beverage"),
        help="Directory containing beverage candidate JSONL/CSV files.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional Markdown report path.",
    )
    parser.add_argument(
        "--price-currency",
        default="KRW",
        help="Required price observation currency for this dry-run.",
    )
    args = parser.parse_args(argv)

    result = run_dry_run(
        data_dir=args.data_dir,
        report_path=args.report,
        price_currency=args.price_currency,
    )
    print(
        "beverage_candidate_dry_run "
        f"accepted={result.accepted_rows} "
        f"warning={result.warning_rows} "
        f"rejected={result.rejected_rows}",
    )
    if result.report_path is not None:
        print(f"report={result.report_path}")
    return result.exit_code


def _load_source_registry(path: Path) -> tuple[SourceRegistry, list[RowResult]]:
    if not path.exists():
        result = RowResult(
            file_name=SOURCE_REGISTRY_FILE,
            line_number=0,
            row_id="<missing>",
            issues=[
                ValidationIssue(
                    Severity.REJECTED,
                    "missing_file",
                    f"required source registry file does not exist: {path}",
                ),
            ],
        )
        return SourceRegistry(set(), set(), {}, []), [result]

    with path.open(newline="", encoding="utf-8") as source_file:
        reader = csv.DictReader(source_file)
        source_rows = list(reader)

    results: list[RowResult] = []
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    urls: set[str] = set()
    source_ids: set[str] = set()
    source_types_by_url: dict[str, str] = {}

    for line_number, row in enumerate(source_rows, start=2):
        row_id = row.get("source_id") or f"line:{line_number}"
        result = RowResult(SOURCE_REGISTRY_FILE, line_number, row_id)
        _require_fields(row, SOURCE_REGISTRY_REQUIRED_FIELDS, result)

        source_id = row.get("source_id", "")
        url = row.get("url", "")
        source_type = row.get("source_type", "")
        confidence = row.get("source_confidence", "")

        if source_id:
            if source_id in seen_ids:
                _reject(
                    result, "duplicate_source_id", f"duplicate source_id {source_id}"
                )
            seen_ids.add(source_id)
            source_ids.add(source_id)

        if url:
            if url in seen_urls:
                _reject(result, "duplicate_source_url", f"duplicate source URL {url}")
            seen_urls.add(url)
            urls.add(url)
            source_types_by_url[url] = source_type

        _validate_source_type(source_type, result)
        _validate_confidence(confidence, result)
        _validate_date(row.get("retrieved_at"), "retrieved_at", result)
        results.append(result)

    return SourceRegistry(urls, source_ids, source_types_by_url, source_rows), results


def _load_jsonl(
    path: Path, row_id_field: str
) -> tuple[list[dict[str, Any]], list[RowResult]]:
    file_name = path.name
    if not path.exists():
        result = RowResult(
            file_name=file_name,
            line_number=0,
            row_id="<missing>",
            issues=[
                ValidationIssue(
                    Severity.REJECTED,
                    "missing_file",
                    f"required JSONL file does not exist: {path}",
                ),
            ],
        )
        return [], [result]

    rows: list[dict[str, Any]] = []
    results: list[RowResult] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            result = RowResult(
                file_name=file_name,
                line_number=line_number,
                row_id=f"line:{line_number}",
            )
            _reject(result, "invalid_json", exc.msg)
            results.append(result)
            continue

        if not isinstance(row, dict):
            result = RowResult(file_name, line_number, f"line:{line_number}")
            _reject(result, "invalid_json_row", "JSONL row must be an object")
            results.append(result)
            continue

        row_id = str(row.get(row_id_field) or f"line:{line_number}")
        rows.append(row)
        results.append(RowResult(file_name, line_number, row_id))

    return rows, results


def _valid_loaded_results(results: list[RowResult]) -> list[RowResult]:
    invalid_codes = {"missing_file", "invalid_json", "invalid_json_row"}
    return [
        result
        for result in results
        if not any(issue.code in invalid_codes for issue in result.issues)
    ]


def _validate_catalog_rows(
    rows: list[dict[str, Any]],
    results: list[RowResult],
    registry: SourceRegistry,
) -> None:
    for row, result in zip(rows, results, strict=True):
        _require_fields(row, CATALOG_REQUIRED_FIELDS, result)
        _validate_candidate_status(row.get("candidate_status"), result)
        _validate_category(row.get("category"), result)
        _validate_confidence(row.get("source_confidence"), result)
        _validate_date(row.get("collected_at"), "collected_at", result)
        _validate_non_empty_list(row.get("source_urls"), "source_urls", result)
        _validate_source_refs(
            source_urls=row.get("source_urls"),
            source_ids=row.get("source_ids"),
            source_type=row.get("source_type"),
            registry=registry,
            result=result,
        )

        candidate_id = row.get("beverage_candidate_id")
        category = row.get("category")
        slug = row.get("beverage_slug")
        if isinstance(candidate_id, str) and isinstance(category, str):
            expected_prefix = f"bev_cand_{category}_"
            if not candidate_id.startswith(expected_prefix):
                _reject(
                    result,
                    "candidate_id_category_mismatch",
                    f"candidate id must start with {expected_prefix}",
                )
        if isinstance(candidate_id, str) and isinstance(slug, str):
            if not candidate_id.endswith(slug):
                _warn(
                    result,
                    "candidate_id_slug_mismatch",
                    "candidate id does not end with beverage_slug",
                )

        _validate_optional_number(row.get("abv"), "abv", result, minimum=0, maximum=100)
        _validate_optional_number(
            row.get("beginner_friendly_score"),
            "beginner_friendly_score",
            result,
            minimum=0,
            maximum=1,
        )


def _validate_flavor_rows(
    rows: list[dict[str, Any]],
    results: list[RowResult],
    registry: SourceRegistry,
) -> None:
    for row, result in zip(rows, results, strict=True):
        _require_fields(row, FLAVOR_REQUIRED_FIELDS, result)
        _validate_candidate_status(row.get("candidate_status"), result)
        _validate_non_empty_list(row.get("source_urls"), "source_urls", result)
        _validate_source_refs(
            source_urls=row.get("source_urls"),
            source_ids=row.get("source_ids"),
            source_type=row.get("source_type"),
            registry=registry,
            result=result,
        )
        if row.get("vector_schema") != "beverage_vector_v1_candidate":
            _reject(
                result,
                "invalid_vector_schema",
                "vector_schema must be beverage_vector_v1_candidate",
            )
        _validate_dimension_values(
            row.get("taste_v1_dimension_values"),
            TASTE_V1_DIMENSIONS,
            "taste_v1_dimension_values",
            result,
        )
        _validate_dimension_values(
            row.get("extended_dimension_values"),
            EXTENDED_BEVERAGE_DIMENSIONS,
            "extended_dimension_values",
            result,
        )
        _validate_number(
            row.get("flavor_confidence_overall"),
            "flavor_confidence_overall",
            result,
            minimum=0,
            maximum=1,
        )


def _validate_knowledge_rows(
    rows: list[dict[str, Any]],
    results: list[RowResult],
    registry: SourceRegistry,
) -> None:
    for row, result in zip(rows, results, strict=True):
        _require_fields(row, KNOWLEDGE_REQUIRED_FIELDS, result)
        _validate_candidate_status(row.get("candidate_status"), result)
        _validate_source_type(row.get("source_type"), result)
        _validate_confidence(row.get("source_confidence"), result)
        _validate_date(row.get("retrieved_at"), "retrieved_at", result)
        _validate_source_refs(
            source_urls=row.get("source_url"),
            source_ids=row.get("source_id") or row.get("source_ids"),
            source_type=row.get("source_type"),
            registry=registry,
            result=result,
        )
        if row.get("language") != "ko":
            _warn(
                result, "unexpected_language", "knowledge candidates should be Korean"
            )
        if row.get("document_type") != "beverage_profile":
            _warn(
                result,
                "unexpected_document_type",
                "expected document_type beverage_profile",
            )


def _validate_price_rows(
    rows: list[dict[str, Any]],
    results: list[RowResult],
    registry: SourceRegistry,
    catalog_ids: set[str],
    price_currency: str,
) -> None:
    for row, result in zip(rows, results, strict=True):
        _require_fields(row, PRICE_REQUIRED_FIELDS, result)
        _validate_source_type(row.get("source_type"), result)
        _validate_date(row.get("observed_at"), "observed_at", result)
        _validate_date(row.get("retrieved_at"), "retrieved_at", result)
        _validate_source_refs(
            source_urls=row.get("source_url"),
            source_ids=row.get("source_id") or row.get("source_ids"),
            source_type=row.get("source_type"),
            registry=registry,
            result=result,
        )

        beverage_candidate_id = row.get("beverage_candidate_id")
        if (
            isinstance(beverage_candidate_id, str)
            and beverage_candidate_id not in catalog_ids
        ):
            _reject(
                result,
                "unknown_beverage_candidate",
                f"{beverage_candidate_id} is not present in catalog candidates",
            )

        if row.get("currency") != price_currency:
            _reject(
                result,
                "invalid_price_currency",
                f"currency must be {price_currency} for this dry-run",
            )
        if price_currency == "KRW" and row.get("market_region") != "KR":
            _reject(
                result,
                "invalid_price_market_region",
                "KRW price observations must use market_region KR",
            )

        _validate_number(row.get("price_min"), "price_min", result, minimum=0)
        _validate_number(row.get("price_max"), "price_max", result, minimum=0)
        _validate_number(row.get("price_value"), "price_value", result, minimum=0)
        _validate_number(
            row.get("confidence"), "confidence", result, minimum=0, maximum=1
        )
        price_min = row.get("price_min")
        price_max = row.get("price_max")
        price_value = row.get("price_value")
        if _is_number(price_min) and _is_number(price_max) and price_min > price_max:
            _reject(result, "invalid_price_range", "price_min must be <= price_max")
        if (
            _is_number(price_min)
            and _is_number(price_max)
            and _is_number(price_value)
            and not price_min <= price_value <= price_max
        ):
            _reject(
                result,
                "invalid_price_value",
                "price_value must be within price_min and price_max",
            )

        price_type = row.get("price_type")
        if not isinstance(price_type, str) or not price_type.strip():
            _reject(result, "missing_price_type", "price_type is required")
        elif SIZE_PATTERN.search(price_type) is None:
            _reject(
                result,
                "missing_package_size",
                "price_type must include package size such as 700ml",
            )


def _validate_catalog_links(
    catalog_ids: set[str],
    flavor_ids: set[str],
    knowledge_ids: set[str],
    rows: list[RowResult],
) -> None:
    missing_flavor = sorted(catalog_ids - flavor_ids)
    missing_knowledge = sorted(catalog_ids - knowledge_ids)
    extra_flavor = sorted(flavor_ids - catalog_ids)
    extra_knowledge = sorted(knowledge_ids - catalog_ids)

    for beverage_id in missing_flavor:
        rows.append(_dataset_rejection("missing_flavor_candidate", beverage_id))
    for beverage_id in missing_knowledge:
        rows.append(_dataset_rejection("missing_knowledge_candidate", beverage_id))
    for beverage_id in extra_flavor:
        rows.append(_dataset_rejection("orphan_flavor_candidate", beverage_id))
    for beverage_id in extra_knowledge:
        rows.append(_dataset_rejection("orphan_knowledge_candidate", beverage_id))


def _validate_duplicates(
    catalog_rows: list[dict[str, Any]],
    flavor_rows: list[dict[str, Any]],
    knowledge_rows: list[dict[str, Any]],
    price_rows: list[dict[str, Any]],
    rows: list[RowResult],
) -> None:
    _append_duplicate_results(
        CATALOG_FILE,
        "beverage_candidate_id",
        [row.get("beverage_candidate_id") for row in catalog_rows],
        rows,
    )
    _append_duplicate_results(
        CATALOG_FILE,
        "beverage_slug",
        [row.get("beverage_slug") for row in catalog_rows],
        rows,
    )
    _append_duplicate_results(
        CATALOG_FILE,
        "normalized_name",
        [
            row.get("normalized_name", "").strip().lower()
            for row in catalog_rows
            if isinstance(row.get("normalized_name"), str)
        ],
        rows,
    )
    _append_duplicate_results(
        FLAVOR_FILE,
        "flavor_candidate_id",
        [row.get("flavor_candidate_id") for row in flavor_rows],
        rows,
    )
    _append_duplicate_results(
        KNOWLEDGE_FILE,
        "knowledge_candidate_id",
        [row.get("knowledge_candidate_id") for row in knowledge_rows],
        rows,
    )
    _append_duplicate_results(
        PRICE_FILE,
        "price_observation_id",
        [row.get("price_observation_id") for row in price_rows],
        rows,
    )

    price_keys = [
        (
            row.get("beverage_candidate_id"),
            row.get("source_url"),
            row.get("observed_at"),
            row.get("currency"),
            row.get("price_value"),
            row.get("price_type"),
        )
        for row in price_rows
    ]
    _append_duplicate_results(
        PRICE_FILE, "price_observation_identity", price_keys, rows
    )


def _append_duplicate_results(
    file_name: str,
    field_name: str,
    values: list[Any],
    rows: list[RowResult],
) -> None:
    cleaned_values = [value for value in values if value not in (None, "")]
    counts = Counter(cleaned_values)
    for value, count in sorted(counts.items(), key=lambda item: str(item[0])):
        if count > 1:
            rows.append(
                RowResult(
                    file_name=file_name,
                    line_number=0,
                    row_id=str(value),
                    issues=[
                        ValidationIssue(
                            Severity.REJECTED,
                            f"duplicate_{field_name}",
                            f"{field_name} appears {count} times",
                        ),
                    ],
                ),
            )


def _require_fields(
    row: dict[str, Any], required_fields: set[str], result: RowResult
) -> None:
    for field_name in sorted(required_fields):
        if field_name not in row or row[field_name] in (None, "", []):
            _reject(result, "missing_required_field", f"{field_name} is required")


def _validate_category(value: Any, result: RowResult) -> None:
    if value not in ALLOWED_CATEGORIES:
        _reject(result, "invalid_category", f"{value!r} is not an allowed category")


def _validate_candidate_status(value: Any, result: RowResult) -> None:
    if value == "needs_review":
        return
    if value == "collected":
        _warn(result, "candidate_status_collected", "row is incomplete reviewer input")
        return
    if value == "approved":
        _reject(
            result, "candidate_status_approved", "automated rows must not be approved"
        )
        return
    _reject(result, "invalid_candidate_status", "candidate_status must be needs_review")


def _validate_source_type(value: Any, result: RowResult) -> None:
    if value in (None, ""):
        return
    if value not in ALLOWED_SOURCE_TYPES:
        _warn(
            result,
            "unknown_source_type",
            f"{value!r} is not in the source policy type list",
        )


def _validate_confidence(value: Any, result: RowResult) -> None:
    if value in (None, ""):
        return
    if value not in ALLOWED_CONFIDENCE_VALUES:
        _warn(
            result, "unknown_confidence", f"{value!r} is not a known confidence value"
        )


def _validate_source_refs(
    source_urls: Any,
    source_ids: Any,
    source_type: Any,
    registry: SourceRegistry,
    result: RowResult,
) -> None:
    urls = _as_list(source_urls)
    ids = _as_list(source_ids)

    if not urls and not ids:
        _reject(
            result,
            "missing_source_reference",
            "at least one source URL or ID is required",
        )
        return

    for source_id in ids:
        if source_id not in registry.source_ids:
            _reject(
                result,
                "unknown_source_id",
                f"{source_id} is not in source_registry.csv",
            )

    for url in urls:
        if url not in registry.urls:
            _reject(
                result, "unknown_source_url", f"{url} is not in source_registry.csv"
            )
            continue
        registry_source_type = registry.source_types_by_url.get(url)
        if (
            source_type
            and registry_source_type
            and source_type != registry_source_type
            and source_type in ALLOWED_SOURCE_TYPES
        ):
            _warn(
                result,
                "source_type_mismatch",
                (
                    f"row source_type {source_type!r} differs from "
                    f"registry {registry_source_type!r}"
                ),
            )


def _validate_non_empty_list(value: Any, field_name: str, result: RowResult) -> None:
    if not isinstance(value, list) or not value:
        _reject(result, "invalid_list", f"{field_name} must be a non-empty list")


def _validate_dimension_values(
    value: Any,
    expected_dimensions: set[str],
    field_name: str,
    result: RowResult,
) -> None:
    if not isinstance(value, dict):
        _reject(result, "invalid_dimension_object", f"{field_name} must be an object")
        return

    actual_dimensions = set(value)
    missing = sorted(expected_dimensions - actual_dimensions)
    extra = sorted(actual_dimensions - expected_dimensions)
    if missing:
        _reject(
            result, "missing_dimensions", f"{field_name} missing {', '.join(missing)}"
        )
    if extra:
        _reject(
            result, "extra_dimensions", f"{field_name} has extra {', '.join(extra)}"
        )

    for dimension, dimension_value in value.items():
        _validate_number(
            dimension_value,
            f"{field_name}.{dimension}",
            result,
            minimum=0,
            maximum=1,
        )


def _validate_optional_number(
    value: Any,
    field_name: str,
    result: RowResult,
    minimum: float | None = None,
    maximum: float | None = None,
) -> None:
    if value is None:
        return
    _validate_number(value, field_name, result, minimum=minimum, maximum=maximum)


def _validate_number(
    value: Any,
    field_name: str,
    result: RowResult,
    minimum: float | None = None,
    maximum: float | None = None,
) -> None:
    if not _is_number(value):
        _reject(result, "invalid_number", f"{field_name} must be a number")
        return
    if minimum is not None and value < minimum:
        _reject(result, "number_too_low", f"{field_name} must be >= {minimum:g}")
    if maximum is not None and value > maximum:
        _reject(result, "number_too_high", f"{field_name} must be <= {maximum:g}")


def _validate_date(value: Any, field_name: str, result: RowResult) -> None:
    if not isinstance(value, str) or not value:
        _reject(result, "invalid_date", f"{field_name} must be an ISO date/datetime")
        return
    try:
        datetime.fromisoformat(value)
    except ValueError:
        _reject(result, "invalid_date", f"{field_name} must be an ISO date/datetime")


def _dataset_rejection(code: str, beverage_id: str) -> RowResult:
    return RowResult(
        file_name="<dataset>",
        line_number=0,
        row_id=beverage_id,
        issues=[
            ValidationIssue(
                Severity.REJECTED,
                code,
                f"{beverage_id} violates catalog/flavor/knowledge one-to-one linking",
            ),
        ],
    )


def _render_report(result: DryRunResult, data_dir: Path) -> str:
    by_file_status: dict[str, Counter[str]] = defaultdict(Counter)
    for row in result.rows:
        by_file_status[row.file_name][row.status] += 1

    lines = [
        "# Beverage Candidate Dry-Run Report",
        "",
        f"- Data directory: `{data_dir}`",
        f"- Accepted rows: {result.accepted_rows}",
        f"- Warning rows: {result.warning_rows}",
        f"- Rejected rows: {result.rejected_rows}",
        f"- Exit code: {result.exit_code}",
        "- DB writes: none",
        "",
        "## Input Counts",
        "",
        "| File | Rows |",
        "|---|---:|",
    ]
    for file_name in sorted(result.candidate_counts):
        lines.append(f"| `{file_name}` | {result.candidate_counts[file_name]} |")

    lines.extend(
        [
            "",
            "## Status Counts",
            "",
            "| File | Accepted | Warning | Rejected |",
            "|---|---:|---:|---:|",
        ]
    )
    for file_name in sorted(by_file_status):
        counts = by_file_status[file_name]
        lines.append(
            "| "
            f"`{file_name}` | "
            f"{counts['accepted']} | "
            f"{counts['warning']} | "
            f"{counts['rejected']} |"
        )

    for status in ("rejected", "warning", "accepted"):
        title = f"{status.capitalize()} Rows"
        rows = [row for row in result.rows if row.status == status]
        lines.extend(["", f"## {title}", ""])
        if not rows:
            lines.append("None.")
            continue
        lines.extend(
            [
                "| File | Line | Row ID | Notes |",
                "|---|---:|---|---|",
            ]
        )
        for row in rows:
            notes = row.messages if row.messages else "ok"
            lines.append(
                "| "
                f"`{row.file_name}` | "
                f"{row.line_number} | "
                f"`{_escape_markdown(str(row.row_id))}` | "
                f"{_escape_markdown(notes)} |"
            )

    lines.append("")
    return "\n".join(lines)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    return []


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _warn(result: RowResult, code: str, message: str) -> None:
    result.issues.append(ValidationIssue(Severity.WARNING, code, message))


def _reject(result: RowResult, code: str, message: str) -> None:
    result.issues.append(ValidationIssue(Severity.REJECTED, code, message))


def _escape_markdown(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
