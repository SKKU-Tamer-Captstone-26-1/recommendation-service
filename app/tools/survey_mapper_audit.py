"""Audit deployed survey-service tokens against the profile mapper."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.services.survey_mapper_audit import (
    audit_deployed_survey_mapper_contract,
    write_survey_mapper_audit_report,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/survey_mapper_audit.json"),
    )
    args = parser.parse_args()

    report = audit_deployed_survey_mapper_contract()
    write_survey_mapper_audit_report(report, args.report)
    print(
        "survey mapper audit "
        f"source_contract={report.source_contract} "
        f"deployed_categories={report.metrics['deployed_categories']} "
        f"mapped_categories={report.metrics['mapped_categories']} "
        f"category_trait_tokens={report.metrics['category_trait_tokens']} "
        f"mapped_category_trait_tokens="
        f"{report.metrics['mapped_category_trait_tokens']} "
        f"flavor_keyword_tokens={report.metrics['flavor_keyword_tokens']} "
        f"mapped_flavor_keyword_tokens="
        f"{report.metrics['mapped_flavor_keyword_tokens']} "
        f"budget_ranges={report.metrics['budget_ranges']} "
        f"mapped_budget_ranges={report.metrics['mapped_budget_ranges']} "
        f"critical={report.critical_count} "
        f"report={args.report}",
    )
    return 1 if report.critical_count else 0


if __name__ == "__main__":
    raise SystemExit(main())

