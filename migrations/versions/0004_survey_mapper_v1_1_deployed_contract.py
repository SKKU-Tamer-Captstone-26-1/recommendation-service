"""survey mapper v1.1 deployed contract

Revision ID: 0004_survey_mapper_v1_1
Revises: 0003_venue_recs
Create Date: 2026-05-27

Title: survey mapper v1.1 deployed contract
Reason: Align derived profile generation with the deployed survey-service
category-based SurveyResult contract, including cognac category normalization,
new budget labels, and new style tokens.
Affected tables: mapper_versions.
Affected docs: docs/recommendation/survey-mapping.md,
docs/recommendation/sync-flow.md, docs/plans/012.md.
Backward compatibility: additive mapper version; old generated profiles still
reference survey_mapper_v1.
Backfill required: none; regenerate profiles from survey-service if v1.1 output
is needed for existing users.
Rollback strategy: deprecate survey_mapper_v1_1 and reactivate
survey_mapper_v1.
Rebuild impact: profile rebuilds after this migration use survey_mapper_v1_1
when ACTIVE_SURVEY_MAPPER is unset or set to the default.
Qdrant impact: profile vectors for regenerated profiles should be reindexed.
Operational risk: low; no raw survey data is copied or mutated.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_survey_mapper_v1_1"
down_revision: str | None = "0003_venue_recs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE mapper_versions
        SET status = 'deprecated',
            updated_at = now()
        WHERE name = 'survey_mapper'
          AND version = 'survey_mapper_v1'
          AND status = 'active'
        """
    )
    op.execute(
        """
        INSERT INTO mapper_versions (
            name,
            version,
            compatible_vector_schema,
            code_hash,
            rules_json,
            status,
            description
        )
        VALUES (
            'survey_mapper',
            'survey_mapper_v1_1',
            'taste_v1',
            NULL,
            $${
              "source_doc": "docs/recommendation/survey-mapping.md",
              "vector_schema": "taste_v1",
              "input_contract": "ontheblock.survey.v1.SurveyResult",
              "snapshot_policy": "redacted_generation_evidence_only",
              "category_aliases": {
                "cognac": "brandy_cognac"
              },
              "budget_aliases": {
                "under_30k": "under_30000",
                "30k_100k": "30000_100000",
                "100k_200k": "100000_200000",
                "over_200k": "over_200000"
              },
              "style_token_source": "survey-service category-key contract 2026-05-26"
            }$$::jsonb,
            'active',
            'Survey mapper aligned to deployed category-key SurveyResult contract.'
        )
        ON CONFLICT ON CONSTRAINT uq_mapper_name_version DO UPDATE
        SET compatible_vector_schema = EXCLUDED.compatible_vector_schema,
            rules_json = EXCLUDED.rules_json,
            status = EXCLUDED.status,
            description = EXCLUDED.description,
            updated_at = now()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE mapper_versions
        SET status = 'deprecated',
            updated_at = now()
        WHERE name = 'survey_mapper'
          AND version = 'survey_mapper_v1_1'
        """
    )
    op.execute(
        """
        UPDATE mapper_versions
        SET status = 'active',
            updated_at = now()
        WHERE name = 'survey_mapper'
          AND version = 'survey_mapper_v1'
        """
    )
