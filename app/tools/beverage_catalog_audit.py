"""Audit reviewed beverage catalog seed quality."""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from app.services.beverage_catalog_audit import (
    BeverageCatalogAuditService,
    audit_seed_records,
    write_catalog_audit_report,
)
from app.services.beverage_import import (
    build_canonical_seed_records,
    load_candidate_artifacts,
)

DEFAULT_SCHEMA_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data/beverage"))
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/beverage_catalog_audit.json"),
    )
    parser.add_argument("--database", action="store_true")
    args = parser.parse_args()

    if args.database:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            report = BeverageCatalogAuditService(session).audit_active_catalog()
    else:
        records = build_canonical_seed_records(
            artifacts=load_candidate_artifacts(args.data_dir),
            vector_schema_version_id=DEFAULT_SCHEMA_ID,
        )
        report = audit_seed_records(
            records,
            source=f"seed:{args.data_dir}",
        )

    write_catalog_audit_report(report, args.report)
    print(
        "beverage catalog audit "
        f"source={report.source} "
        f"active_beverages={report.metrics['active_beverages']} "
        f"critical={report.critical_count} "
        f"warnings={report.warning_count} "
        f"report={args.report}",
    )
    return 1 if report.critical_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
