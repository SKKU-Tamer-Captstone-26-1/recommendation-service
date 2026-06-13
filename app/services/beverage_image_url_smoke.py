from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.models.catalog import BeverageItem
from app.services.beverage_import import (
    build_canonical_seed_records,
    load_candidate_artifacts,
)

DEFAULT_VECTOR_SCHEMA_VERSION_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
DEFAULT_IMAGE_URL_SMOKE_USER_AGENT = (
    "ONTHEBLOCK-recommendation-service/0.1 image-url-smoke"
)


@dataclass(frozen=True)
class BeverageImageUrlTarget:
    beverage_id: str | None
    catalog_key: str | None
    category: str
    name_en: str | None
    display_name_ko: str
    image_url: str
    original_image_url: str | None
    source_url: str | None
    image_kind: str | None
    attribution_required: bool | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "beverage_id": self.beverage_id,
            "catalog_key": self.catalog_key,
            "category": self.category,
            "name_en": self.name_en,
            "display_name_ko": self.display_name_ko,
            "image_url": self.image_url,
            "original_image_url": self.original_image_url,
            "source_url": self.source_url,
            "image_kind": self.image_kind,
            "attribution_required": self.attribution_required,
        }


@dataclass(frozen=True)
class ImageUrlHttpResponse:
    status_code: int
    content_type: str | None
    final_url: str | None
    method: str


@dataclass(frozen=True)
class BeverageImageUrlCheck:
    target: BeverageImageUrlTarget
    status: str
    status_code: int | None
    content_type: str | None
    final_url: str | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target.to_dict(),
            "status": self.status,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "final_url": self.final_url,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class BeverageImageUrlSmokeReport:
    generated_at: str
    source: str
    checked_urls: int
    passed_urls: int
    failed_urls: int
    results: tuple[BeverageImageUrlCheck, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "source": self.source,
            "checked_urls": self.checked_urls,
            "passed_urls": self.passed_urls,
            "failed_urls": self.failed_urls,
            "results": [result.to_dict() for result in self.results],
        }


ImageUrlFetcher = Callable[[str], ImageUrlHttpResponse]


def image_url_targets_from_seed(
    data_dir: Path,
    *,
    vector_schema_version_id: uuid.UUID = DEFAULT_VECTOR_SCHEMA_VERSION_ID,
) -> tuple[BeverageImageUrlTarget, ...]:
    records = build_canonical_seed_records(
        artifacts=load_candidate_artifacts(data_dir),
        vector_schema_version_id=vector_schema_version_id,
    )
    return image_url_targets_from_beverages(record.beverage for record in records)


def image_url_targets_from_beverages(
    beverages: Iterable[BeverageItem],
) -> tuple[BeverageImageUrlTarget, ...]:
    targets: list[BeverageImageUrlTarget] = []
    for beverage in sorted(beverages, key=_beverage_sort_key):
        metadata = beverage.metadata_json or {}
        image_url = _optional_string(metadata.get("image_url"))
        if image_url is None:
            continue
        image_metadata = metadata.get("image")
        if not isinstance(image_metadata, dict):
            image_metadata = {}
        targets.append(
            BeverageImageUrlTarget(
                beverage_id=str(beverage.id) if beverage.id is not None else None,
                catalog_key=_optional_string(metadata.get("catalog_key")),
                category=beverage.category,
                name_en=beverage.name_en,
                display_name_ko=beverage.name_ko,
                image_url=image_url,
                original_image_url=_optional_string(
                    image_metadata.get("original_image_url"),
                ),
                source_url=_optional_string(
                    metadata.get("image_source_url")
                    or image_metadata.get("source_url"),
                ),
                image_kind=_optional_string(
                    metadata.get("image_kind") or image_metadata.get("image_kind"),
                ),
                attribution_required=_optional_bool(
                    image_metadata.get("attribution_required"),
                ),
            ),
        )
    return tuple(targets)


def deduplicate_image_url_targets(
    targets: Iterable[BeverageImageUrlTarget],
) -> tuple[BeverageImageUrlTarget, ...]:
    deduplicated: dict[str, BeverageImageUrlTarget] = {}
    for target in targets:
        deduplicated.setdefault(target.image_url, target)
    return tuple(deduplicated.values())


def run_beverage_image_url_smoke(
    *,
    targets: Iterable[BeverageImageUrlTarget],
    source: str,
    timeout_seconds: float = 10.0,
    user_agent: str = DEFAULT_IMAGE_URL_SMOKE_USER_AGENT,
    request_interval_seconds: float = 0.0,
    fetcher: ImageUrlFetcher | None = None,
    generated_at: datetime | None = None,
) -> BeverageImageUrlSmokeReport:
    resolved_targets = tuple(targets)
    if fetcher is not None:
        return _run_checks(
            targets=resolved_targets,
            source=source,
            fetcher=fetcher,
            request_interval_seconds=request_interval_seconds,
            generated_at=generated_at,
        )

    with httpx.Client(
        timeout=timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": user_agent},
    ) as client:
        return _run_checks(
            targets=resolved_targets,
            source=source,
            fetcher=lambda url: _fetch_image_url(client, url),
            request_interval_seconds=request_interval_seconds,
            generated_at=generated_at,
        )


def write_beverage_image_url_smoke_report(
    report: BeverageImageUrlSmokeReport,
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )


def _run_checks(
    *,
    targets: tuple[BeverageImageUrlTarget, ...],
    source: str,
    fetcher: ImageUrlFetcher,
    request_interval_seconds: float,
    generated_at: datetime | None,
) -> BeverageImageUrlSmokeReport:
    results: list[BeverageImageUrlCheck] = []
    for index, target in enumerate(targets):
        if index > 0 and request_interval_seconds > 0:
            time.sleep(request_interval_seconds)
        try:
            response = fetcher(target.image_url)
        except Exception as exc:  # noqa: BLE001 - smoke reports request failures.
            results.append(
                BeverageImageUrlCheck(
                    target=target,
                    status="failed",
                    status_code=None,
                    content_type=None,
                    final_url=None,
                    detail=f"request_error={type(exc).__name__}: {exc}",
                ),
            )
            continue

        passed, detail = _evaluate_image_response(response)
        results.append(
            BeverageImageUrlCheck(
                target=target,
                status="passed" if passed else "failed",
                status_code=response.status_code,
                content_type=response.content_type,
                final_url=response.final_url,
                detail=detail,
            ),
        )

    failed_urls = sum(1 for result in results if result.status == "failed")
    timestamp = (generated_at or datetime.now(UTC)).isoformat()
    return BeverageImageUrlSmokeReport(
        generated_at=timestamp,
        source=source,
        checked_urls=len(results),
        passed_urls=len(results) - failed_urls,
        failed_urls=failed_urls,
        results=tuple(results),
    )


def _fetch_image_url(client: httpx.Client, url: str) -> ImageUrlHttpResponse:
    response = client.head(url)
    content_type = response.headers.get("content-type")
    if response.status_code in {403, 405} or content_type is None:
        with client.stream("GET", url) as get_response:
            return ImageUrlHttpResponse(
                status_code=get_response.status_code,
                content_type=get_response.headers.get("content-type"),
                final_url=str(get_response.url),
                method="GET",
            )
    return ImageUrlHttpResponse(
        status_code=response.status_code,
        content_type=content_type,
        final_url=str(response.url),
        method="HEAD",
    )


def _evaluate_image_response(response: ImageUrlHttpResponse) -> tuple[bool, str]:
    if response.status_code < 200 or response.status_code >= 400:
        return False, f"bad_status_code={response.status_code} method={response.method}"
    content_type = (response.content_type or "").split(";", maxsplit=1)[0].lower()
    if not content_type.startswith("image/"):
        return (
            False,
            f"unsupported_content_type={response.content_type} "
            f"method={response.method}",
        )
    return True, f"ok method={response.method}"


def _beverage_sort_key(beverage: BeverageItem) -> tuple[str, str, str]:
    metadata = beverage.metadata_json or {}
    catalog_key = _optional_string(metadata.get("catalog_key")) or ""
    return (beverage.category, beverage.name_en or beverage.name_ko, catalog_key)


def _optional_string(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None
