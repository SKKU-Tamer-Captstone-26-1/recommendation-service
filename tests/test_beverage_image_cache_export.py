import json
from datetime import UTC, datetime
from pathlib import Path

from app.services.beverage_image_cache_export import (
    ImageDownloadResponse,
    export_beverage_image_cache,
    image_cache_assets_from_seed,
)


def test_image_cache_assets_from_seed_deduplicates_shared_images() -> None:
    assets = image_cache_assets_from_seed(
        Path("data/beverage"),
        gcs_bucket="ontheblock-beverage-images-staging",
    )

    assert 0 < len(assets) < 60
    assert any(
        asset.image_candidate_id
        == "bev_image_whiskey_buffalo_trace_bourbon_product_001"
        and asset.catalog_keys == ("whiskey.buffalo_trace_bourbon",)
        and asset.gcs_uri
        == (
            "gs://ontheblock-beverage-images-staging/beverage-images/v1/"
            "bev_image_whiskey_buffalo_trace_bourbon_product_001.jpg"
        )
        for asset in assets
    )
    whiskey_fallback = next(
        asset
        for asset in assets
        if asset.image_candidate_id
        == "bev_image_whiskey_category_representative_001"
    )
    assert len(whiskey_fallback.catalog_keys) > 1


def test_image_cache_assets_from_seed_uses_cdn_display_url() -> None:
    assets = image_cache_assets_from_seed(
        Path("data/beverage"),
        image_cdn_base_url="https://cdn.example.test",
    )

    buffalo_trace = next(
        asset
        for asset in assets
        if asset.image_candidate_id
        == "bev_image_whiskey_buffalo_trace_bourbon_product_001"
    )

    assert buffalo_trace.display_url == (
        "https://cdn.example.test/beverage-images/v1/"
        "bev_image_whiskey_buffalo_trace_bourbon_product_001.jpg"
    )
    assert buffalo_trace.display_url_source == "operator_managed_cache"
    assert buffalo_trace.original_image_url == (
        "https://commons.wikimedia.org/wiki/Special:FilePath/"
        "Buffalo_Trace_bourbon_whiskey.jpg"
    )


def test_export_beverage_image_cache_manifest_only(tmp_path: Path) -> None:
    assets = image_cache_assets_from_seed(Path("data/beverage"))[:2]
    manifest_path = tmp_path / "manifest.json"

    report = export_beverage_image_cache(
        assets=assets,
        source="test",
        output_dir=tmp_path / "images",
        manifest_path=manifest_path,
        download=False,
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert report.total_assets == 2
    assert report.exported_assets == 0
    assert report.skipped_assets == 2
    assert report.failed_assets == 0
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text())
    assert payload["generated_at"] == "2026-01-01T00:00:00+00:00"
    assert payload["items"][0]["status"] == "skipped"
    assert not Path(report.items[0].output_path).exists()


def test_export_beverage_image_cache_downloads_images(tmp_path: Path) -> None:
    assets = image_cache_assets_from_seed(Path("data/beverage"))[:1]
    manifest_path = tmp_path / "manifest.json"

    report = export_beverage_image_cache(
        assets=assets,
        source="test",
        output_dir=tmp_path / "images",
        manifest_path=manifest_path,
        download=True,
        downloader=lambda url: ImageDownloadResponse(
            status_code=200,
            content_type="image/jpeg",
            content=b"fake-image-bytes",
            final_url=url,
        ),
    )

    assert report.exported_assets == 1
    assert report.failed_assets == 0
    output_path = Path(report.items[0].output_path)
    assert output_path.exists()
    assert output_path.read_bytes() == b"fake-image-bytes"


def test_export_beverage_image_cache_reports_failed_download(
    tmp_path: Path,
) -> None:
    assets = image_cache_assets_from_seed(Path("data/beverage"))[:1]
    manifest_path = tmp_path / "manifest.json"

    report = export_beverage_image_cache(
        assets=assets,
        source="test",
        output_dir=tmp_path / "images",
        manifest_path=manifest_path,
        download=True,
        downloader=lambda url: ImageDownloadResponse(
            status_code=200,
            content_type="text/html",
            content=b"<html></html>",
            final_url=url,
        ),
    )

    assert report.exported_assets == 0
    assert report.failed_assets == 1
    assert "unsupported_content_type=text/html" in report.items[0].detail
    assert not Path(report.items[0].output_path).exists()
