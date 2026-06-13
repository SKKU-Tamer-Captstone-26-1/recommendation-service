from __future__ import annotations

import json
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
DEFAULT_IMAGE_CACHE_EXPORT_USER_AGENT = (
    "ONTHEBLOCK-recommendation-service/0.1 image-cache-export"
)


@dataclass(frozen=True)
class BeverageImageCacheAsset:
    cache_key: str
    cache_policy: str
    display_url: str
    display_url_source: str
    original_image_url: str
    source_url: str
    source_type: str
    license: str
    license_url: str
    attribution: str
    attribution_required: bool
    image_candidate_id: str
    image_kind: str
    category: str
    catalog_keys: tuple[str, ...]
    beverage_ids: tuple[str, ...]
    names_en: tuple[str, ...]
    display_names_ko: tuple[str, ...]
    gcs_uri: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cache_key": self.cache_key,
            "cache_policy": self.cache_policy,
            "display_url": self.display_url,
            "display_url_source": self.display_url_source,
            "original_image_url": self.original_image_url,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "license": self.license,
            "license_url": self.license_url,
            "attribution": self.attribution,
            "attribution_required": self.attribution_required,
            "image_candidate_id": self.image_candidate_id,
            "image_kind": self.image_kind,
            "category": self.category,
            "catalog_keys": list(self.catalog_keys),
            "beverage_ids": list(self.beverage_ids),
            "names_en": list(self.names_en),
            "display_names_ko": list(self.display_names_ko),
            "gcs_uri": self.gcs_uri,
        }


@dataclass(frozen=True)
class ImageDownloadResponse:
    status_code: int
    content_type: str | None
    content: bytes
    final_url: str | None


@dataclass(frozen=True)
class BeverageImageCacheExportItem:
    asset: BeverageImageCacheAsset
    status: str
    output_path: str
    bytes_written: int
    content_type: str | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset.to_dict(),
            "status": self.status,
            "output_path": self.output_path,
            "bytes_written": self.bytes_written,
            "content_type": self.content_type,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class BeverageImageCacheExportReport:
    generated_at: str
    source: str
    output_dir: str
    manifest_path: str
    total_assets: int
    exported_assets: int
    skipped_assets: int
    failed_assets: int
    download_enabled: bool
    items: tuple[BeverageImageCacheExportItem, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "source": self.source,
            "output_dir": self.output_dir,
            "manifest_path": self.manifest_path,
            "total_assets": self.total_assets,
            "exported_assets": self.exported_assets,
            "skipped_assets": self.skipped_assets,
            "failed_assets": self.failed_assets,
            "download_enabled": self.download_enabled,
            "items": [item.to_dict() for item in self.items],
        }


ImageDownloader = Callable[[str], ImageDownloadResponse]


def image_cache_assets_from_seed(
    data_dir: Path,
    *,
    image_cdn_base_url: str | None = None,
    gcs_bucket: str | None = None,
    vector_schema_version_id: uuid.UUID = DEFAULT_VECTOR_SCHEMA_VERSION_ID,
) -> tuple[BeverageImageCacheAsset, ...]:
    records = build_canonical_seed_records(
        artifacts=load_candidate_artifacts(data_dir),
        vector_schema_version_id=vector_schema_version_id,
        image_cdn_base_url=image_cdn_base_url,
    )
    return image_cache_assets_from_beverages(
        (record.beverage for record in records),
        gcs_bucket=gcs_bucket,
    )


def image_cache_assets_from_beverages(
    beverages: Iterable[BeverageItem],
    *,
    gcs_bucket: str | None = None,
) -> tuple[BeverageImageCacheAsset, ...]:
    grouped: dict[str, list[BeverageItem]] = {}
    for beverage in sorted(beverages, key=_beverage_sort_key):
        image = _image_metadata(beverage)
        cache_key = _required_string(image, "cache_key")
        grouped.setdefault(cache_key, []).append(beverage)

    assets: list[BeverageImageCacheAsset] = []
    for cache_key, grouped_beverages in sorted(grouped.items()):
        first = grouped_beverages[0]
        image = _image_metadata(first)
        _ensure_cache_group_consistency(cache_key, grouped_beverages)
        assets.append(
            BeverageImageCacheAsset(
                cache_key=cache_key,
                cache_policy=_required_string(image, "cache_policy"),
                display_url=_required_string(image, "image_url"),
                display_url_source=_required_string(image, "display_url_source"),
                original_image_url=_required_string(image, "original_image_url"),
                source_url=_required_string(image, "source_url"),
                source_type=_required_string(image, "source_type"),
                license=_required_string(image, "license"),
                license_url=_required_string(image, "license_url"),
                attribution=_required_string(image, "attribution"),
                attribution_required=bool(image.get("attribution_required")),
                image_candidate_id=_required_string(image, "image_candidate_id"),
                image_kind=_required_string(image, "image_kind"),
                category=first.category,
                catalog_keys=tuple(
                    _required_string(beverage.metadata_json, "catalog_key")
                    for beverage in grouped_beverages
                ),
                beverage_ids=tuple(str(beverage.id) for beverage in grouped_beverages),
                names_en=tuple(
                    beverage.name_en or beverage.name_ko
                    for beverage in grouped_beverages
                ),
                display_names_ko=tuple(
                    beverage.name_ko for beverage in grouped_beverages
                ),
                gcs_uri=_gcs_uri(gcs_bucket, cache_key),
            ),
        )
    return tuple(assets)


def export_beverage_image_cache(
    *,
    assets: Iterable[BeverageImageCacheAsset],
    source: str,
    output_dir: Path,
    manifest_path: Path,
    download: bool,
    timeout_seconds: float = 15.0,
    user_agent: str = DEFAULT_IMAGE_CACHE_EXPORT_USER_AGENT,
    downloader: ImageDownloader | None = None,
    generated_at: datetime | None = None,
) -> BeverageImageCacheExportReport:
    resolved_assets = tuple(assets)
    if not download or downloader is not None:
        report = _export_assets(
            assets=resolved_assets,
            source=source,
            output_dir=output_dir,
            manifest_path=manifest_path,
            download=download,
            downloader=downloader,
            generated_at=generated_at,
        )
    else:
        with httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": user_agent},
        ) as client:
            report = _export_assets(
                assets=resolved_assets,
                source=source,
                output_dir=output_dir,
                manifest_path=manifest_path,
                download=True,
                downloader=lambda url: _download_image(client, url),
                generated_at=generated_at,
            )

    write_beverage_image_cache_export_report(report, manifest_path)
    return report


def write_beverage_image_cache_export_report(
    report: BeverageImageCacheExportReport,
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )


def _export_assets(
    *,
    assets: tuple[BeverageImageCacheAsset, ...],
    source: str,
    output_dir: Path,
    manifest_path: Path,
    download: bool,
    downloader: ImageDownloader | None,
    generated_at: datetime | None,
) -> BeverageImageCacheExportReport:
    items: list[BeverageImageCacheExportItem] = []
    for asset in assets:
        output_path = output_dir / asset.cache_key
        if not download:
            items.append(
                BeverageImageCacheExportItem(
                    asset=asset,
                    status="skipped",
                    output_path=str(output_path),
                    bytes_written=0,
                    content_type=None,
                    detail="manifest_only",
                ),
            )
            continue
        if downloader is None:
            raise ValueError("downloader is required when download is enabled")
        try:
            response = downloader(asset.original_image_url)
        except Exception as exc:  # noqa: BLE001 - export report records failures.
            items.append(
                BeverageImageCacheExportItem(
                    asset=asset,
                    status="failed",
                    output_path=str(output_path),
                    bytes_written=0,
                    content_type=None,
                    detail=f"download_error={type(exc).__name__}: {exc}",
                ),
            )
            continue

        passed, detail = _validate_download_response(response)
        if not passed:
            items.append(
                BeverageImageCacheExportItem(
                    asset=asset,
                    status="failed",
                    output_path=str(output_path),
                    bytes_written=0,
                    content_type=response.content_type,
                    detail=detail,
                ),
            )
            continue

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        items.append(
            BeverageImageCacheExportItem(
                asset=asset,
                status="exported",
                output_path=str(output_path),
                bytes_written=len(response.content),
                content_type=response.content_type,
                detail=detail,
            ),
        )

    exported_assets = sum(1 for item in items if item.status == "exported")
    skipped_assets = sum(1 for item in items if item.status == "skipped")
    failed_assets = sum(1 for item in items if item.status == "failed")
    timestamp = (generated_at or datetime.now(UTC)).isoformat()
    return BeverageImageCacheExportReport(
        generated_at=timestamp,
        source=source,
        output_dir=str(output_dir),
        manifest_path=str(manifest_path),
        total_assets=len(items),
        exported_assets=exported_assets,
        skipped_assets=skipped_assets,
        failed_assets=failed_assets,
        download_enabled=download,
        items=tuple(items),
    )


def _download_image(client: httpx.Client, url: str) -> ImageDownloadResponse:
    response = client.get(url)
    return ImageDownloadResponse(
        status_code=response.status_code,
        content_type=response.headers.get("content-type"),
        content=response.content,
        final_url=str(response.url),
    )


def _validate_download_response(
    response: ImageDownloadResponse,
) -> tuple[bool, str]:
    if response.status_code < 200 or response.status_code >= 400:
        return False, f"bad_status_code={response.status_code}"
    content_type = (response.content_type or "").split(";", maxsplit=1)[0].lower()
    if not content_type.startswith("image/"):
        return False, f"unsupported_content_type={response.content_type}"
    if not response.content:
        return False, "empty_image_response"
    return True, f"ok final_url={response.final_url or ''}".strip()


def _image_metadata(beverage: BeverageItem) -> dict[str, Any]:
    metadata = beverage.metadata_json or {}
    image = metadata.get("image")
    if not isinstance(image, dict):
        raise ValueError(f"beverage {beverage.id} is missing image metadata")
    return image


def _ensure_cache_group_consistency(
    cache_key: str,
    beverages: list[BeverageItem],
) -> None:
    first = _image_metadata(beverages[0])
    fields = (
        "original_image_url",
        "source_url",
        "license",
        "license_url",
        "attribution",
        "image_candidate_id",
    )
    for beverage in beverages[1:]:
        image = _image_metadata(beverage)
        for field in fields:
            if image.get(field) != first.get(field):
                raise ValueError(
                    f"cache_key {cache_key} has inconsistent image field {field}",
                )


def _gcs_uri(gcs_bucket: str | None, cache_key: str) -> str | None:
    if not gcs_bucket:
        return None
    normalized = gcs_bucket.removeprefix("gs://").strip("/")
    if not normalized:
        return None
    return f"gs://{normalized}/{cache_key}"


def _beverage_sort_key(beverage: BeverageItem) -> tuple[str, str, str]:
    metadata = beverage.metadata_json or {}
    catalog_key = metadata.get("catalog_key")
    return (
        beverage.category,
        catalog_key if isinstance(catalog_key, str) else "",
        beverage.name_en or beverage.name_ko,
    )


def _required_string(metadata: dict[str, Any], field: str) -> str:
    value = metadata.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"image metadata missing required string field: {field}")
    return value
