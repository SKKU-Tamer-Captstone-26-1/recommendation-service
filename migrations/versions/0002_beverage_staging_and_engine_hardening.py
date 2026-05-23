"""beverage staging and engine hardening

Revision ID: 0002_beverage_engine
Revises: 0001_initial_foundation
Create Date: 2026-05-23

Title: beverage staging and engine hardening
Reason: Add review-only beverage candidate staging tables and interaction
idempotency before promoting a reviewed MVP seed subset into canonical
recommendation-owned tables.
Affected tables: recommendation_staging.*, recommendation_interactions.
Affected docs: docs/plans/002.md, docs/database/erd.md,
docs/beverage/beverage-staging-db-mapping.md.
Backward compatibility: additive only.
Backfill required: no.
Rollback strategy: drop staging schema and idempotency index.
Rebuild impact: none; canonical vectors remain in PostgreSQL.
Qdrant impact: none.
Operational risk: low; no canonical map/place/auth/survey tables are touched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0002_beverage_engine"
down_revision: str | None = "0001_initial_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STAGING_SCHEMA = "recommendation_staging"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def _candidate_common_columns() -> list[sa.Column]:
    return [
        _uuid_pk(),
        sa.Column("collection_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", sa.String(length=180), nullable=False),
        sa.Column("beverage_candidate_id", sa.String(length=180), nullable=True),
        sa.Column("canonical_name_en", sa.String(length=255), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("candidate_status", sa.String(length=50), nullable=False),
        sa.Column("validation_status", sa.String(length=50), nullable=False),
        sa.Column(
            "validation_errors_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
    ]


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {STAGING_SCHEMA}")

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        uq_recommendation_interactions_idempotency_key_not_null
        ON recommendation_interactions (idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )

    op.create_table(
        "beverage_collection_runs",
        _uuid_pk(),
        sa.Column("run_id", sa.String(length=180), nullable=False),
        sa.Column("agent", sa.String(length=180), nullable=True),
        sa.Column("task_prompt", sa.Text(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_manifest_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("import_status", sa.String(length=50), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_beverage_collection_runs_run_id"),
        schema=STAGING_SCHEMA,
    )

    op.create_table(
        "beverage_catalog_candidates",
        *_candidate_common_columns(),
        sa.ForeignKeyConstraint(
            ["collection_run_id"],
            [f"{STAGING_SCHEMA}.beverage_collection_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id",
            name="uq_beverage_catalog_candidates_candidate_id",
        ),
        schema=STAGING_SCHEMA,
    )
    op.create_index(
        "ix_beverage_catalog_candidates_category",
        "beverage_catalog_candidates",
        ["category", "validation_status"],
        schema=STAGING_SCHEMA,
    )

    op.create_table(
        "beverage_flavor_profile_candidates",
        *_candidate_common_columns(),
        sa.ForeignKeyConstraint(
            ["collection_run_id"],
            [f"{STAGING_SCHEMA}.beverage_collection_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id",
            name="uq_beverage_flavor_candidates_candidate_id",
        ),
        schema=STAGING_SCHEMA,
    )
    op.create_index(
        "ix_beverage_flavor_candidates_beverage",
        "beverage_flavor_profile_candidates",
        ["beverage_candidate_id", "validation_status"],
        schema=STAGING_SCHEMA,
    )

    op.create_table(
        "beverage_knowledge_candidates",
        *_candidate_common_columns(),
        sa.Column("language", sa.String(length=20), nullable=True),
        sa.Column("document_type", sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(
            ["collection_run_id"],
            [f"{STAGING_SCHEMA}.beverage_collection_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id",
            name="uq_beverage_knowledge_candidates_candidate_id",
        ),
        schema=STAGING_SCHEMA,
    )
    op.create_index(
        "ix_beverage_knowledge_candidates_beverage",
        "beverage_knowledge_candidates",
        ["beverage_candidate_id", "validation_status"],
        schema=STAGING_SCHEMA,
    )

    op.create_table(
        "beverage_price_observation_candidates",
        *_candidate_common_columns(),
        sa.Column("market_region", sa.String(length=40), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("price_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("observed_at", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ["collection_run_id"],
            [f"{STAGING_SCHEMA}.beverage_collection_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id",
            name="uq_beverage_price_candidates_candidate_id",
        ),
        schema=STAGING_SCHEMA,
    )
    op.create_index(
        "ix_beverage_price_candidates_market",
        "beverage_price_observation_candidates",
        ["market_region", "currency", "validation_status"],
        schema=STAGING_SCHEMA,
    )

    op.create_table(
        "beverage_source_refs",
        _uuid_pk(),
        sa.Column("collection_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.String(length=180), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("usage_lanes", sa.String(length=255), nullable=True),
        sa.Column("source_confidence", sa.String(length=50), nullable=True),
        sa.Column("retrieved_at", sa.Date(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["collection_run_id"],
            [f"{STAGING_SCHEMA}.beverage_collection_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", name="uq_beverage_source_refs_source_id"),
        schema=STAGING_SCHEMA,
    )
    op.create_index(
        "ix_beverage_source_refs_url",
        "beverage_source_refs",
        ["url"],
        schema=STAGING_SCHEMA,
    )

    op.create_table(
        "beverage_candidate_import_errors",
        _uuid_pk(),
        sa.Column("collection_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_lane", sa.String(length=80), nullable=False),
        sa.Column("candidate_id", sa.String(length=180), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["collection_run_id"],
            [f"{STAGING_SCHEMA}.beverage_collection_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=STAGING_SCHEMA,
    )
    op.create_index(
        "ix_beverage_candidate_import_errors_run",
        "beverage_candidate_import_errors",
        ["collection_run_id", "candidate_lane"],
        schema=STAGING_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_beverage_candidate_import_errors_run",
        table_name="beverage_candidate_import_errors",
        schema=STAGING_SCHEMA,
    )
    op.drop_table("beverage_candidate_import_errors", schema=STAGING_SCHEMA)
    op.drop_index(
        "ix_beverage_source_refs_url",
        table_name="beverage_source_refs",
        schema=STAGING_SCHEMA,
    )
    op.drop_table("beverage_source_refs", schema=STAGING_SCHEMA)
    op.drop_index(
        "ix_beverage_price_candidates_market",
        table_name="beverage_price_observation_candidates",
        schema=STAGING_SCHEMA,
    )
    op.drop_table("beverage_price_observation_candidates", schema=STAGING_SCHEMA)
    op.drop_index(
        "ix_beverage_knowledge_candidates_beverage",
        table_name="beverage_knowledge_candidates",
        schema=STAGING_SCHEMA,
    )
    op.drop_table("beverage_knowledge_candidates", schema=STAGING_SCHEMA)
    op.drop_index(
        "ix_beverage_flavor_candidates_beverage",
        table_name="beverage_flavor_profile_candidates",
        schema=STAGING_SCHEMA,
    )
    op.drop_table("beverage_flavor_profile_candidates", schema=STAGING_SCHEMA)
    op.drop_index(
        "ix_beverage_catalog_candidates_category",
        table_name="beverage_catalog_candidates",
        schema=STAGING_SCHEMA,
    )
    op.drop_table("beverage_catalog_candidates", schema=STAGING_SCHEMA)
    op.drop_table("beverage_collection_runs", schema=STAGING_SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {STAGING_SCHEMA}")
    op.execute(
        """
        DROP INDEX IF EXISTS
        uq_recommendation_interactions_idempotency_key_not_null
        """
    )
