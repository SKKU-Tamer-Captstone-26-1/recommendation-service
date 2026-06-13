"""scoring v2 budget and distance feature strategies

Revision ID: 0005_scoring_v2
Revises: 0004_survey_mapper_v1_1
Create Date: 2026-06-07

Title: scoring v2 budget and distance feature strategies
Reason: Add a versioned scoring config for catalog price-aware beverage budget
features and route-ready venue distance metadata without mutating scoring_v1.
Affected tables: scoring_configs.
Affected docs: docs/recommendation/recommendation-logic.md,
docs/recommendation/map-read-model.md, docs/plans/015.md.
Backward compatibility: additive scoring version; scoring_v1 remains available
for rollback through ACTIVE_SCORING_CONFIG=scoring_v1.
Backfill required: none. Existing recommendation logs keep their original
scoring_config_id.
Rollback strategy: deprecate scoring_v2 rows and set ACTIVE_SCORING_CONFIG back
to scoring_v1.
Rebuild impact: profile regeneration after switching ACTIVE_SCORING_CONFIG can
store scoring_v2 references. Existing profiles remain valid.
Qdrant impact: none.
Operational risk: medium; beverage ranking can change when scoring_v2 is active.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_scoring_v2"
down_revision: str | None = "0004_survey_mapper_v1_1"
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
            'scoring_v2',
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
              "template_version": "reason_template_v2",
              "source_doc": "docs/recommendation/recommendation-logic.md",
              "budget_feature_strategy": "catalog_price_range_soft_v1",
              "reason_codes": [
                "MATCHES_VANILLA_CARAMEL",
                "MATCHES_SMOKY_PROFILE",
                "BEGINNER_FRIENDLY",
                "WITHIN_BUDGET",
                "ADJACENT_DISCOVERY"
              ]
            }$$::jsonb,
            'active',
            'Budget-aware beverage scoring using reviewed catalog KRW price ranges.'
        ),
        (
            'default_scoring',
            'scoring_v2',
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
        WHERE version = 'scoring_v2'
        """
    )
