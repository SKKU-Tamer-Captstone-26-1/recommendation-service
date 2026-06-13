from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.profile_generation import (
    CATEGORY_BASE_WEIGHTS,
    DEPLOYED_SURVEY_BUDGET_RANGES,
    DEPLOYED_SURVEY_CATEGORIES,
    DEPLOYED_SURVEY_CATEGORY_TRAITS,
    DEPLOYED_SURVEY_FLAVOR_KEYWORDS,
    DEPLOYED_SURVEY_LEVELS,
    KEYWORD_DIMENSION_WEIGHTS,
    canonicalize_survey_budget_range,
    canonicalize_survey_categories,
    canonicalize_survey_category,
)

CRITICAL = "critical"


@dataclass(frozen=True)
class SurveyMapperAuditIssue:
    severity: str
    code: str
    message: str
    token: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "token": self.token,
        }


@dataclass(frozen=True)
class SurveyMapperAuditReport:
    generated_at: str
    source_contract: str
    metrics: dict[str, Any]
    issues: tuple[SurveyMapperAuditIssue, ...]

    @property
    def critical_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == CRITICAL)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "source_contract": self.source_contract,
            "metrics": self.metrics,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def audit_deployed_survey_mapper_contract(
    *,
    categories: tuple[str, ...] = DEPLOYED_SURVEY_CATEGORIES,
    category_traits: dict[str, tuple[str, ...]] = DEPLOYED_SURVEY_CATEGORY_TRAITS,
    flavor_keywords: tuple[str, ...] = DEPLOYED_SURVEY_FLAVOR_KEYWORDS,
    budget_ranges: tuple[str, ...] = DEPLOYED_SURVEY_BUDGET_RANGES,
    generated_at: datetime | None = None,
) -> SurveyMapperAuditReport:
    issues: list[SurveyMapperAuditIssue] = []
    canonical_categories = canonicalize_survey_categories(list(categories))

    for category in categories:
        canonical_category = canonicalize_survey_category(category)
        if canonical_category not in CATEGORY_BASE_WEIGHTS:
            issues.append(
                SurveyMapperAuditIssue(
                    severity=CRITICAL,
                    code="unmapped_survey_category",
                    message=(
                        "deployed survey category does not map to category base "
                        "weights"
                    ),
                    token=category,
                ),
            )

    trait_tokens: list[str] = []
    trait_categories: list[str] = []
    for category, traits in sorted(category_traits.items()):
        canonical_category = canonicalize_survey_category(category)
        trait_categories.append(canonical_category)
        if canonical_category not in CATEGORY_BASE_WEIGHTS:
            issues.append(
                SurveyMapperAuditIssue(
                    severity=CRITICAL,
                    code="unmapped_trait_category",
                    message="survey trait category does not map to base weights",
                    token=category,
                ),
            )
        for trait in traits:
            trait_tokens.append(trait)
            if trait not in KEYWORD_DIMENSION_WEIGHTS:
                issues.append(
                    SurveyMapperAuditIssue(
                        severity=CRITICAL,
                        code="unmapped_survey_trait",
                        message="deployed survey category trait has no vector mapping",
                        token=trait,
                    ),
                )

    for keyword in flavor_keywords:
        if keyword not in KEYWORD_DIMENSION_WEIGHTS:
            issues.append(
                SurveyMapperAuditIssue(
                    severity=CRITICAL,
                    code="unmapped_flavor_keyword",
                    message="deployed survey flavor keyword has no vector mapping",
                    token=keyword,
                ),
            )

    canonical_budget_ranges = []
    for budget_range in budget_ranges:
        canonical_budget = canonicalize_survey_budget_range(budget_range)
        if canonical_budget is None:
            issues.append(
                SurveyMapperAuditIssue(
                    severity=CRITICAL,
                    code="unmapped_budget_range",
                    message="deployed survey budget token has no canonical mapping",
                    token=budget_range,
                ),
            )
        else:
            canonical_budget_ranges.append(canonical_budget)

    metrics = {
        "deployed_levels": len(DEPLOYED_SURVEY_LEVELS),
        "deployed_categories": len(categories),
        "mapped_categories": len(canonical_categories),
        "category_trait_categories": len(set(trait_categories)),
        "category_trait_tokens": len(trait_tokens),
        "mapped_category_trait_tokens": sum(
            1 for token in trait_tokens if token in KEYWORD_DIMENSION_WEIGHTS
        ),
        "flavor_keyword_tokens": len(flavor_keywords),
        "mapped_flavor_keyword_tokens": sum(
            1 for token in flavor_keywords if token in KEYWORD_DIMENSION_WEIGHTS
        ),
        "budget_ranges": len(budget_ranges),
        "mapped_budget_ranges": len(canonical_budget_ranges),
        "canonical_categories": canonical_categories,
        "canonical_budget_ranges": canonical_budget_ranges,
    }
    return SurveyMapperAuditReport(
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        source_contract="ontheblock.survey.v1.SurveyResult",
        metrics=metrics,
        issues=tuple(sorted(issues, key=lambda issue: (issue.code, issue.token or ""))),
    )


def write_survey_mapper_audit_report(
    report: SurveyMapperAuditReport,
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )

