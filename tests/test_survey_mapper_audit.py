from app.services.survey_mapper_audit import (
    CRITICAL,
    audit_deployed_survey_mapper_contract,
)


def test_deployed_survey_mapper_contract_has_full_token_coverage() -> None:
    report = audit_deployed_survey_mapper_contract()

    assert report.critical_count == 0
    assert report.metrics["deployed_categories"] == 5
    assert report.metrics["mapped_categories"] == 5
    assert report.metrics["category_trait_tokens"] == 20
    assert report.metrics["mapped_category_trait_tokens"] == 20
    assert report.metrics["flavor_keyword_tokens"] == 9
    assert report.metrics["mapped_flavor_keyword_tokens"] == 9
    assert report.metrics["budget_ranges"] == 4
    assert report.metrics["mapped_budget_ranges"] == 4
    assert "brandy_cognac" in report.metrics["canonical_categories"]


def test_survey_mapper_audit_detects_unmapped_deployed_tokens() -> None:
    report = audit_deployed_survey_mapper_contract(
        categories=("whiskey", "new_category"),
        category_traits={"whiskey": ("bourbon_character", "new_trait")},
        flavor_keywords=("vanilla_caramel", "new_keyword"),
        budget_ranges=("under_30k", ""),
    )

    critical_codes = {
        issue.code for issue in report.issues if issue.severity == CRITICAL
    }
    assert "unmapped_survey_category" in critical_codes
    assert "unmapped_survey_trait" in critical_codes
    assert "unmapped_flavor_keyword" in critical_codes
    assert "unmapped_budget_range" in critical_codes

