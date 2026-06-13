"""Smoke-check app-visible beverage image URLs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.models.catalog import BeverageItem
from app.services.beverage_image_url_smoke import (
    DEFAULT_IMAGE_URL_SMOKE_USER_AGENT,
    deduplicate_image_url_targets,
    image_url_targets_from_beverages,
    image_url_targets_from_seed,
    run_beverage_image_url_smoke,
    write_beverage_image_url_smoke_report,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data/beverage"))
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/beverage_image_url_smoke.json"),
    )
    parser.add_argument("--database", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--user-agent", default=DEFAULT_IMAGE_URL_SMOKE_USER_AGENT)
    parser.add_argument("--request-interval-seconds", type=float, default=0.25)
    parser.add_argument("--max-urls", type=int, default=None)
    parser.add_argument("--include-duplicate-urls", action="store_true")
    args = parser.parse_args()

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
        targets = image_url_targets_from_beverages(beverages)
    else:
        source = f"seed:{args.data_dir}"
        targets = image_url_targets_from_seed(args.data_dir)

    original_target_count = len(targets)
    if not args.include_duplicate_urls:
        targets = deduplicate_image_url_targets(targets)

    if args.max_urls is not None:
        targets = targets[: args.max_urls]

    report = run_beverage_image_url_smoke(
        targets=targets,
        source=source,
        timeout_seconds=args.timeout_seconds,
        user_agent=args.user_agent,
        request_interval_seconds=args.request_interval_seconds,
    )
    write_beverage_image_url_smoke_report(report, args.report)

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))
    else:
        print(
            "beverage image url smoke "
            f"source={report.source} "
            f"beverage_targets={original_target_count} "
            f"checked_urls={report.checked_urls} "
            f"passed_urls={report.passed_urls} "
            f"failed_urls={report.failed_urls} "
            f"report={args.report}",
        )
        for result in report.results:
            if result.status == "failed":
                print(
                    "beverage image url failed "
                    f"catalog_key={result.target.catalog_key} "
                    f"name_en={result.target.name_en} "
                    f"image_url={result.target.image_url} "
                    f"detail={result.detail}",
                )
    return 1 if report.failed_urls else 0


if __name__ == "__main__":
    raise SystemExit(main())
