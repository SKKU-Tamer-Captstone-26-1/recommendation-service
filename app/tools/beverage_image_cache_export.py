"""Export beverage image cache manifest and optional local image files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.models.catalog import BeverageItem
from app.services.beverage_image_cache_export import (
    DEFAULT_IMAGE_CACHE_EXPORT_USER_AGENT,
    export_beverage_image_cache,
    image_cache_assets_from_beverages,
    image_cache_assets_from_seed,
)

DEFAULT_OUTPUT_DIR = Path("/private/tmp/recommendation-beverage-image-cache")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data/beverage"))
    parser.add_argument("--database", action="store_true")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--cdn-base-url", default=None)
    parser.add_argument("--gcs-bucket", default=None)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--user-agent", default=DEFAULT_IMAGE_CACHE_EXPORT_USER_AGENT)
    args = parser.parse_args()

    settings = get_settings()
    cdn_base_url = args.cdn_base_url or settings.beverage_image_cdn_base_url
    manifest_path = args.manifest or (args.output_dir / "manifest.json")

    if args.database:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            beverages = tuple(
                session.scalars(
                    select(BeverageItem)
                    .where(BeverageItem.active.is_(True))
                    .order_by(
                        BeverageItem.category,
                        BeverageItem.name_en,
                        BeverageItem.name_ko,
                        BeverageItem.id,
                    ),
                ).all(),
            )
        source = "database:active_beverages"
        assets = image_cache_assets_from_beverages(
            beverages,
            gcs_bucket=args.gcs_bucket,
        )
    else:
        source = f"seed:{args.data_dir}"
        assets = image_cache_assets_from_seed(
            args.data_dir,
            image_cdn_base_url=cdn_base_url,
            gcs_bucket=args.gcs_bucket,
        )

    report = export_beverage_image_cache(
        assets=assets,
        source=source,
        output_dir=args.output_dir,
        manifest_path=manifest_path,
        download=args.download,
        timeout_seconds=args.timeout_seconds,
        user_agent=args.user_agent,
    )

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))
    else:
        print(
            "beverage image cache export "
            f"source={report.source} "
            f"assets={report.total_assets} "
            f"exported={report.exported_assets} "
            f"skipped={report.skipped_assets} "
            f"failed={report.failed_assets} "
            f"download={report.download_enabled} "
            f"manifest={report.manifest_path}",
        )
        if args.gcs_bucket:
            print(
                "upload hint "
                f"gcloud storage cp -r {args.output_dir / 'beverage-images'} "
                f"gs://{args.gcs_bucket.removeprefix('gs://').strip('/')}/",
            )
    return 1 if report.failed_assets else 0


if __name__ == "__main__":
    raise SystemExit(main())
