"""scoring v3 category-aware beverage similarity

Revision ID: 0007_scoring_v3
Revises: 0006_beverage_images
Create Date: 2026-06-07

Title: scoring v3 category-aware beverage similarity
Reason: Add a versioned scoring config that emphasizes category-relevant taste
dimensions for beverage recommendations while keeping scoring_v2 available as a
rollback target.
Affected tables: scoring_configs.
Affected docs: docs/recommendation/recommendation-logic.md,
docs/operations/release-gate.md, docs/plans/020.md.
Backward compatibility: additive scoring version; scoring_v1 and scoring_v2
remain available for rollback through ACTIVE_SCORING_CONFIG.
Backfill required: none. Existing recommendation logs keep their original
scoring_config_id.
Rollback strategy: deprecate scoring_v3 rows and set ACTIVE_SCORING_CONFIG back
to scoring_v2 or scoring_v1.
Rebuild impact: profile regeneration after switching ACTIVE_SCORING_CONFIG can
store scoring_v3 references. Existing profiles remain valid.
Qdrant impact: none.
Operational risk: medium; beverage ranking can change when scoring_v3 is active.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_scoring_v3"
down_revision: str | None = "0006_beverage_images"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO scoring_configs (
            name,
            version,
            target_type,
            category,
            weights_json,
            reason_code_rules_json,
            status,
            description
        )
        VALUES
        (
            'default_scoring',
            'scoring_v3',
            'beverage',
            'all',
            $${
              "taste_similarity_weighted": 0.65,
              "budget_fit": 0.10,
              "category_fit": 0.10,
              "experience_fit": 0.05,
              "popularity_or_quality": 0.05,
              "diversity_adjustment": 0.05
            }$$::jsonb,
            $${
              "template_version": "reason_template_v3",
              "source_doc": "docs/recommendation/recommendation-logic.md",
              "budget_feature_strategy": "catalog_price_range_soft_v1",
              "similarity_strategy": "category_weighted_similarity_v1",
              "category_dimension_weights": {
                "whiskey": {
                  "sweet": 1.15,
                  "woody": 1.25,
                  "smoky": 1.35,
                  "body": 1.15,
                  "alcohol_intensity": 1.10
                },
                "wine": {
                  "fruity": 1.20,
                  "acidity": 1.25,
                  "tannin": 1.20,
                  "body": 1.15,
                  "floral": 1.10
                },
                "beer": {
                  "bitterness": 1.25,
                  "carbonation": 1.20,
                  "body": 1.10,
                  "roasted": 1.25,
                  "acidity": 1.10
                },
                "cocktail": {
                  "sweet": 1.15,
                  "acidity": 1.25,
                  "herbal": 1.20,
                  "carbonation": 1.10,
                  "alcohol_intensity": 1.15
                },
                "brandy_cognac": {
                  "dried_fruit": 1.25,
                  "woody": 1.25,
                  "sweet": 1.15,
                  "body": 1.15,
                  "spicy": 1.10
                },
                "gin": {
                  "herbal": 1.30,
                  "floral": 1.20,
                  "bitterness": 1.15,
                  "alcohol_intensity": 1.10,
                  "acidity": 1.10
                },
                "liqueur": {
                  "sweet": 1.30,
                  "roasted": 1.20,
                  "nutty": 1.15,
                  "body": 1.15,
                  "dried_fruit": 1.10
                },
                "rum": {
                  "sweet": 1.20,
                  "spicy": 1.20,
                  "body": 1.15,
                  "woody": 1.15,
                  "fruity": 1.10
                },
                "sake_shochu": {
                  "floral": 1.20,
                  "fruity": 1.15,
                  "body": 1.10,
                  "acidity": 1.10,
                  "alcohol_intensity": 1.10
                },
                "tequila_mezcal": {
                  "smoky": 1.25,
                  "herbal": 1.20,
                  "acidity": 1.15,
                  "alcohol_intensity": 1.15,
                  "spicy": 1.10
                },
                "traditional_korean_alcohol": {
                  "sweet": 1.20,
                  "acidity": 1.20,
                  "body": 1.10,
                  "carbonation": 1.10,
                  "nutty": 1.10
                },
                "vodka": {
                  "alcohol_intensity": 1.20,
                  "body": 1.10,
                  "acidity": 1.05,
                  "carbonation": 1.05
                }
              },
              "reason_codes": [
                "MATCHES_VANILLA_CARAMEL",
                "MATCHES_SMOKY_PROFILE",
                "BEGINNER_FRIENDLY",
                "WITHIN_BUDGET",
                "ADJACENT_DISCOVERY"
              ]
            }$$::jsonb,
            'active',
            'Category-aware beverage scoring using category-relevant taste dimension weights.'
        ),
        (
            'default_scoring',
            'scoring_v3',
            'venue',
            'all',
            $${
              "taste_similarity_weighted": 0.35,
              "distance_fit": 0.20,
              "budget_fit": 0.10,
              "availability_confidence": 0.15,
              "price_confidence": 0.10,
              "freshness_adjustment": 0.10
            }$$::jsonb,
            $${
              "template_version": "venue_reason_template_v2",
              "source_doc": "docs/recommendation/map-read-model.md",
              "distance_feature_strategy": "route_ready_distance_feature_v1",
              "reason_codes": [
                "NEARBY_VENUE",
                "WITHIN_BUDGET",
                "LIKELY_AVAILABLE",
                "FRESH_INVENTORY",
                "BALANCED_BEST"
              ]
            }$$::jsonb,
            'active',
            'Venue scoring metadata aligned to route-ready distance features.'
        )
        ON CONFLICT ON CONSTRAINT uq_scoring_config_identity DO UPDATE
        SET weights_json = EXCLUDED.weights_json,
            reason_code_rules_json = EXCLUDED.reason_code_rules_json,
            status = EXCLUDED.status,
            description = EXCLUDED.description,
            updated_at = now()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE scoring_configs
        SET status = 'deprecated',
            updated_at = now()
        WHERE version = 'scoring_v3'
        """
    )
