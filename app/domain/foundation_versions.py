from typing import Any

from app.domain.vector_schema import (
    TASTE_V1_DIMENSION_COUNT,
    TASTE_V1_DIMENSIONS,
    TASTE_V1_DISTANCE_METRIC,
    TASTE_V1_NAME,
    TASTE_V1_VALUE_MAX,
    TASTE_V1_VALUE_MIN,
)

ACTIVE_STATUS = "active"
SURVEY_MAPPER_V1 = "survey_mapper_v1"
SCORING_V1 = "scoring_v1"


def taste_v1_vector_schema_payload() -> dict[str, Any]:
    return {
        "name": "taste",
        "version": TASTE_V1_NAME,
        "dimension_count": TASTE_V1_DIMENSION_COUNT,
        "distance_metric": TASTE_V1_DISTANCE_METRIC,
        "status": ACTIVE_STATUS,
        "dimensions_json": {
            "schema_name": TASTE_V1_NAME,
            "value_range": {
                "min": TASTE_V1_VALUE_MIN,
                "max": TASTE_V1_VALUE_MAX,
            },
            "dimensions": [
                {
                    "index": dimension.index,
                    "name": dimension.name,
                    "meaning": dimension.meaning,
                }
                for dimension in TASTE_V1_DIMENSIONS
            ],
        },
    }


def survey_mapper_v1_payload() -> dict[str, Any]:
    return {
        "name": "survey_mapper",
        "version": SURVEY_MAPPER_V1,
        "compatible_vector_schema": TASTE_V1_NAME,
        "status": ACTIVE_STATUS,
        "rules_json": {
            "source_doc": "docs/recommendation/survey-mapping.md",
            "vector_schema": TASTE_V1_NAME,
            "input_contract": "survey_v1",
            "snapshot_policy": "redacted_generation_evidence_only",
        },
    }


def scoring_v1_payloads() -> tuple[dict[str, Any], ...]:
    return (
        {
            "name": "default_scoring",
            "version": SCORING_V1,
            "target_type": "beverage",
            "category": "all",
            "status": ACTIVE_STATUS,
            "weights_json": {
                "taste_similarity_weighted": 0.65,
                "budget_fit": 0.10,
                "category_fit": 0.10,
                "experience_fit": 0.05,
                "popularity_or_quality": 0.05,
                "diversity_adjustment": 0.05,
            },
            "reason_code_rules_json": {
                "template_version": "reason_template_v1",
                "source_doc": "docs/recommendation/recommendation-logic.md",
                "reason_codes": [
                    "MATCHES_VANILLA_CARAMEL",
                    "MATCHES_SMOKY_PROFILE",
                    "BEGINNER_FRIENDLY",
                    "WITHIN_BUDGET",
                    "ADJACENT_DISCOVERY",
                ],
            },
        },
        {
            "name": "default_scoring",
            "version": SCORING_V1,
            "target_type": "venue",
            "category": "all",
            "status": ACTIVE_STATUS,
            "weights_json": {
                "taste_similarity_weighted": 0.35,
                "distance_fit": 0.20,
                "budget_fit": 0.10,
                "availability_confidence": 0.15,
                "price_confidence": 0.10,
                "freshness_adjustment": 0.10,
            },
            "reason_code_rules_json": {
                "template_version": "reason_template_v1",
                "source_doc": "docs/recommendation/map-read-model.md",
                "reason_codes": [
                    "NEARBY_VENUE",
                    "WITHIN_BUDGET",
                    "LIKELY_AVAILABLE",
                    "FRESH_INVENTORY",
                    "BALANCED_BEST",
                ],
            },
        },
    )


__all__ = [
    "ACTIVE_STATUS",
    "SCORING_V1",
    "SURVEY_MAPPER_V1",
    "scoring_v1_payloads",
    "survey_mapper_v1_payload",
    "taste_v1_vector_schema_payload",
]
