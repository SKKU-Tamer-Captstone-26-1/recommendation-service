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
DEPRECATED_STATUS = "deprecated"
SURVEY_MAPPER_V1 = "survey_mapper_v1"
SURVEY_MAPPER_V1_1 = "survey_mapper_v1_1"
SCORING_V1 = "scoring_v1"
SCORING_V2 = "scoring_v2"
SCORING_V3 = "scoring_v3"

CATEGORY_WEIGHTED_SIMILARITY_V1 = "category_weighted_similarity_v1"

CATEGORY_DIMENSION_WEIGHTS_V1: dict[str, dict[str, float]] = {
    "whiskey": {
        "sweet": 1.15,
        "woody": 1.25,
        "smoky": 1.35,
        "body": 1.15,
        "alcohol_intensity": 1.10,
    },
    "wine": {
        "fruity": 1.20,
        "acidity": 1.25,
        "tannin": 1.20,
        "body": 1.15,
        "floral": 1.10,
    },
    "beer": {
        "bitterness": 1.25,
        "carbonation": 1.20,
        "body": 1.10,
        "roasted": 1.25,
        "acidity": 1.10,
    },
    "cocktail": {
        "sweet": 1.15,
        "acidity": 1.25,
        "herbal": 1.20,
        "carbonation": 1.10,
        "alcohol_intensity": 1.15,
    },
    "brandy_cognac": {
        "dried_fruit": 1.25,
        "woody": 1.25,
        "sweet": 1.15,
        "body": 1.15,
        "spicy": 1.10,
    },
    "gin": {
        "herbal": 1.30,
        "floral": 1.20,
        "bitterness": 1.15,
        "alcohol_intensity": 1.10,
        "acidity": 1.10,
    },
    "liqueur": {
        "sweet": 1.30,
        "roasted": 1.20,
        "nutty": 1.15,
        "body": 1.15,
        "dried_fruit": 1.10,
    },
    "rum": {
        "sweet": 1.20,
        "spicy": 1.20,
        "body": 1.15,
        "woody": 1.15,
        "fruity": 1.10,
    },
    "sake_shochu": {
        "floral": 1.20,
        "fruity": 1.15,
        "body": 1.10,
        "acidity": 1.10,
        "alcohol_intensity": 1.10,
    },
    "tequila_mezcal": {
        "smoky": 1.25,
        "herbal": 1.20,
        "acidity": 1.15,
        "alcohol_intensity": 1.15,
        "spicy": 1.10,
    },
    "traditional_korean_alcohol": {
        "sweet": 1.20,
        "acidity": 1.20,
        "body": 1.10,
        "carbonation": 1.10,
        "nutty": 1.10,
    },
    "vodka": {
        "alcohol_intensity": 1.20,
        "body": 1.10,
        "acidity": 1.05,
        "carbonation": 1.05,
    },
}


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
        "status": DEPRECATED_STATUS,
        "rules_json": {
            "source_doc": "docs/recommendation/survey-mapping.md",
            "vector_schema": TASTE_V1_NAME,
            "input_contract": "survey_v1",
            "snapshot_policy": "redacted_generation_evidence_only",
        },
    }


def survey_mapper_v1_1_payload() -> dict[str, Any]:
    return {
        "name": "survey_mapper",
        "version": SURVEY_MAPPER_V1_1,
        "compatible_vector_schema": TASTE_V1_NAME,
        "status": ACTIVE_STATUS,
        "rules_json": {
            "source_doc": "docs/recommendation/survey-mapping.md",
            "vector_schema": TASTE_V1_NAME,
            "input_contract": "ontheblock.survey.v1.SurveyResult",
            "snapshot_policy": "redacted_generation_evidence_only",
            "normalization": {
                "cognac": "brandy_cognac",
                "under_30k": "under_30000",
                "30k_100k": "30000_100000",
                "100k_200k": "100000_200000",
                "over_200k": "over_200000",
            },
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


def scoring_v2_payloads() -> tuple[dict[str, Any], ...]:
    return (
        {
            "name": "default_scoring",
            "version": SCORING_V2,
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
                "template_version": "reason_template_v2",
                "source_doc": "docs/recommendation/recommendation-logic.md",
                "budget_feature_strategy": "catalog_price_range_soft_v1",
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
            "version": SCORING_V2,
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
                "template_version": "venue_reason_template_v2",
                "source_doc": "docs/recommendation/map-read-model.md",
                "distance_feature_strategy": "route_ready_distance_feature_v1",
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


def scoring_v3_payloads() -> tuple[dict[str, Any], ...]:
    return (
        {
            "name": "default_scoring",
            "version": SCORING_V3,
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
                "template_version": "reason_template_v3",
                "source_doc": "docs/recommendation/recommendation-logic.md",
                "budget_feature_strategy": "catalog_price_range_soft_v1",
                "similarity_strategy": CATEGORY_WEIGHTED_SIMILARITY_V1,
                "category_dimension_weights": CATEGORY_DIMENSION_WEIGHTS_V1,
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
            "version": SCORING_V3,
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
                "template_version": "venue_reason_template_v2",
                "source_doc": "docs/recommendation/map-read-model.md",
                "distance_feature_strategy": "route_ready_distance_feature_v1",
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
    "CATEGORY_DIMENSION_WEIGHTS_V1",
    "CATEGORY_WEIGHTED_SIMILARITY_V1",
    "DEPRECATED_STATUS",
    "SCORING_V1",
    "SCORING_V2",
    "SCORING_V3",
    "SURVEY_MAPPER_V1",
    "SURVEY_MAPPER_V1_1",
    "scoring_v1_payloads",
    "scoring_v2_payloads",
    "scoring_v3_payloads",
    "survey_mapper_v1_1_payload",
    "survey_mapper_v1_payload",
    "taste_v1_vector_schema_payload",
]
