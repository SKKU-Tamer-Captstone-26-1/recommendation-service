import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.models.catalog import BeverageItem
from app.services.beverage_image_url_smoke import (
    BeverageImageUrlTarget,
    ImageUrlHttpResponse,
    deduplicate_image_url_targets,
    image_url_targets_from_beverages,
    image_url_targets_from_seed,
    run_beverage_image_url_smoke,
)


def test_image_url_targets_from_seed_extracts_all_mvp_beverage_images() -> None:
    targets = image_url_targets_from_seed(Path("data/beverage"))

    assert len(targets) == 60
    assert all(target.image_url.startswith("https://") for target in targets)
    assert all(target.display_name_ko for target in targets)
    assert all(target.image_kind for target in targets)
    assert any(
        target.catalog_key == "whiskey.buffalo_trace_bourbon"
        and target.image_kind == "licensed_product_representative"
        for target in targets
    )


def test_image_url_targets_from_beverages_ignores_missing_image_url() -> None:
    targets = image_url_targets_from_beverages(
        (
            _beverage(
                catalog_key="whiskey.fixture",
                image_url="https://example.test/fixture.jpg",
            ),
            _beverage(catalog_key="gin.no_image", image_url=None),
        ),
    )

    assert len(targets) == 1
    assert targets[0].catalog_key == "whiskey.fixture"


def test_deduplicate_image_url_targets_keeps_first_target_per_url() -> None:
    first = _target("https://example.test/shared.jpg")
    duplicate = BeverageImageUrlTarget(
        beverage_id=str(uuid.uuid4()),
        catalog_key="gin.fixture",
        category="gin",
        name_en="Fixture Gin",
        display_name_ko="픽스처 진",
        image_url=first.image_url,
        original_image_url=first.original_image_url,
        source_url=first.source_url,
        image_kind="category_representative",
        attribution_required=True,
    )
    unique = _target("https://example.test/unique.jpg")

    targets = deduplicate_image_url_targets((first, duplicate, unique))

    assert targets == (first, unique)


def test_run_beverage_image_url_smoke_passes_image_content_type() -> None:
    targets = (
        _target("https://example.test/fixture.jpg"),
        _target("https://example.test/fixture.png"),
    )

    report = run_beverage_image_url_smoke(
        targets=targets,
        source="test",
        fetcher=lambda url: ImageUrlHttpResponse(
            status_code=200,
            content_type="image/jpeg; charset=binary",
            final_url=url,
            method="HEAD",
        ),
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert report.checked_urls == 2
    assert report.passed_urls == 2
    assert report.failed_urls == 0
    assert report.to_dict()["generated_at"] == "2026-01-01T00:00:00+00:00"


def test_run_beverage_image_url_smoke_fails_non_image_content_type() -> None:
    report = run_beverage_image_url_smoke(
        targets=(_target("https://example.test/not-image"),),
        source="test",
        fetcher=lambda url: ImageUrlHttpResponse(
            status_code=200,
            content_type="text/html",
            final_url=url,
            method="GET",
        ),
    )

    assert report.failed_urls == 1
    assert report.results[0].status == "failed"
    assert "unsupported_content_type=text/html" in report.results[0].detail


def test_run_beverage_image_url_smoke_fails_bad_status_code() -> None:
    report = run_beverage_image_url_smoke(
        targets=(_target("https://example.test/missing.jpg"),),
        source="test",
        fetcher=lambda url: ImageUrlHttpResponse(
            status_code=404,
            content_type="image/jpeg",
            final_url=url,
            method="HEAD",
        ),
    )

    assert report.failed_urls == 1
    assert report.results[0].status == "failed"
    assert "bad_status_code=404" in report.results[0].detail


def test_run_beverage_image_url_smoke_records_request_errors() -> None:
    def _failing_fetcher(url: str) -> ImageUrlHttpResponse:
        raise RuntimeError(f"cannot reach {url}")

    report = run_beverage_image_url_smoke(
        targets=(_target("https://example.test/down.jpg"),),
        source="test",
        fetcher=_failing_fetcher,
    )

    assert report.failed_urls == 1
    assert report.results[0].status == "failed"
    assert "request_error=RuntimeError" in report.results[0].detail


def _target(image_url: str) -> BeverageImageUrlTarget:
    return BeverageImageUrlTarget(
        beverage_id=str(uuid.uuid4()),
        catalog_key="whiskey.fixture",
        category="whiskey",
        name_en="Fixture Whiskey",
        display_name_ko="픽스처 위스키",
        image_url=image_url,
        original_image_url=image_url,
        source_url="https://commons.wikimedia.org/wiki/File:Fixture.jpg",
        image_kind="licensed_product_representative",
        attribution_required=True,
    )


def _beverage(
    *,
    catalog_key: str,
    image_url: str | None,
) -> BeverageItem:
    metadata = {
        "catalog_key": catalog_key,
        "image": {
            "image_kind": "licensed_product_representative",
            "source_url": "https://commons.wikimedia.org/wiki/File:Fixture.jpg",
            "attribution_required": True,
        },
    }
    if image_url is not None:
        metadata.update(
            {
                "image_url": image_url,
                "image_kind": "licensed_product_representative",
                "image_source_url": (
                    "https://commons.wikimedia.org/wiki/File:Fixture.jpg"
                ),
            },
        )
    return BeverageItem(
        id=uuid.uuid4(),
        category=catalog_key.split(".", maxsplit=1)[0],
        name_ko="픽스처",
        name_en="Fixture",
        active=True,
        metadata_json=metadata,
    )
