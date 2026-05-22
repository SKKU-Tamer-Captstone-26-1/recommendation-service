"""initial foundation

Revision ID: 0001_initial_foundation
Revises:
Create Date: 2026-05-08

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql


revision: str = "0001_initial_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def _uuid_pk() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "vector_schema_versions",
        _uuid_pk(),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("dimensions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dimension_count", sa.Integer(), nullable=False),
        sa.Column("distance_metric", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_vector_schema_name_version"),
    )

    op.create_table(
        "mapper_versions",
        _uuid_pk(),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("compatible_vector_schema", sa.String(length=100), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=True),
        sa.Column("rules_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_mapper_name_version"),
    )

    op.create_table(
        "scoring_configs",
        _uuid_pk(),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("weights_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason_code_rules_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", "target_type", "category", name="uq_scoring_config_identity"),
    )

    op.create_table(
        "user_profile_state",
        sa.Column("external_user_id", sa.String(length=128), nullable=False),
        sa.Column("active_profile_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("last_survey_response_id", sa.String(length=128), nullable=True),
        sa.Column("last_survey_response_revision", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("external_user_id"),
    )

    op.create_table(
        "taste_profile_revisions",
        _uuid_pk(),
        sa.Column("external_user_id", sa.String(length=128), nullable=False),
        sa.Column("profile_revision", sa.Integer(), nullable=False),
        sa.Column("survey_response_id", sa.String(length=128), nullable=False),
        sa.Column("survey_version", sa.String(length=100), nullable=False),
        sa.Column("survey_response_revision", sa.Integer(), nullable=False),
        sa.Column("mapper_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vector_schema_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scoring_config_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("taste_vector", postgresql.ARRAY(sa.Float()), nullable=False),
        sa.Column("taste_vector_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("preferred_categories", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("preferred_keywords", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("budget_range", sa.String(length=100), nullable=True),
        sa.Column("experience_level", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generation_metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["external_user_id"], ["user_profile_state.external_user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mapper_version_id"], ["mapper_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["scoring_config_id"], ["scoring_configs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vector_schema_version_id"], ["vector_schema_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_user_id", "profile_revision", name="uq_profile_revision_per_user"),
        sa.UniqueConstraint(
            "external_user_id",
            "survey_response_id",
            "survey_response_revision",
            "mapper_version_id",
            name="uq_profile_generation_identity",
        ),
    )
    op.create_foreign_key(
        "fk_user_profile_state_active_profile_revision",
        "user_profile_state",
        "taste_profile_revisions",
        ["active_profile_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_taste_profile_revisions_user_revision",
        "taste_profile_revisions",
        ["external_user_id", "profile_revision"],
    )
    op.create_index(
        "ix_taste_profile_revisions_survey_mapper",
        "taste_profile_revisions",
        ["survey_response_id", "survey_response_revision", "mapper_version_id"],
    )

    op.create_table(
        "survey_source_snapshots",
        _uuid_pk(),
        sa.Column("profile_revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("survey_response_id", sa.String(length=128), nullable=False),
        sa.Column("survey_version", sa.String(length=100), nullable=False),
        sa.Column("survey_response_revision", sa.Integer(), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=128), nullable=False),
        sa.Column("snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["profile_revision_id"], ["taste_profile_revisions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_revision_id", name="uq_survey_snapshot_profile_revision"),
    )

    op.create_table(
        "recommendation_vectors",
        _uuid_pk(),
        sa.Column("owner_type", sa.String(length=50), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vector_schema_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vector", postgresql.ARRAY(sa.Float()), nullable=False),
        sa.Column("vector_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_hash", sa.String(length=128), nullable=False),
        sa.Column("source_metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["vector_schema_version_id"], ["vector_schema_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_type",
            "owner_id",
            "vector_schema_version_id",
            "source_hash",
            name="uq_recommendation_vector_identity",
        ),
    )
    op.create_index(
        "ix_recommendation_vectors_owner",
        "recommendation_vectors",
        ["owner_type", "owner_id", "vector_schema_version_id"],
    )

    op.create_table(
        "qdrant_points",
        _uuid_pk(),
        sa.Column("vector_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_name", sa.String(length=128), nullable=False),
        sa.Column("point_id", sa.String(length=128), nullable=False),
        sa.Column("payload_hash", sa.String(length=128), nullable=False),
        sa.Column("index_status", sa.String(length=50), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["vector_id"], ["recommendation_vectors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collection_name", "point_id", name="uq_qdrant_collection_point"),
    )
    op.create_index("ix_qdrant_points_vector_id", "qdrant_points", ["vector_id"])

    op.create_table(
        "beverage_items",
        _uuid_pk(),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("name_ko", sa.String(length=255), nullable=False),
        sa.Column("name_en", sa.String(length=255), nullable=True),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("abv", sa.Float(), nullable=True),
        sa.Column("price_min_krw", sa.Integer(), nullable=True),
        sa.Column("price_max_krw", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("search_document", postgresql.TSVECTOR(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_beverage_items_category_active", "beverage_items", ["category", "active"])
    op.create_index("ix_beverage_items_price_range", "beverage_items", ["price_min_krw", "price_max_krw"])
    op.create_index("ix_beverage_items_search_document", "beverage_items", ["search_document"], postgresql_using="gin")
    op.execute("CREATE INDEX ix_beverage_items_name_ko_trgm ON beverage_items USING gin (name_ko gin_trgm_ops)")
    op.execute("CREATE INDEX ix_beverage_items_name_en_trgm ON beverage_items USING gin (name_en gin_trgm_ops)")

    op.create_table(
        "venue_snapshots",
        _uuid_pk(),
        sa.Column("place_id", sa.String(length=128), nullable=False),
        sa.Column("place_revision", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("place_type", sa.String(length=100), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column(
            "location",
            Geography(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("publication_status", sa.String(length=50), nullable=True),
        sa.Column("search_document", postgresql.TSVECTOR(), nullable=True),
        sa.Column("snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_event_id", sa.String(length=128), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("stale_after", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_venue_snapshots_place_revision", "venue_snapshots", ["place_id", "place_revision"])
    op.create_index("ix_venue_snapshots_status_stale", "venue_snapshots", ["status", "stale_after"])
    op.create_index("ix_venue_snapshots_location", "venue_snapshots", ["location"], postgresql_using="gist")
    op.create_index("ix_venue_snapshots_search_document", "venue_snapshots", ["search_document"], postgresql_using="gin")
    op.execute("CREATE INDEX ix_venue_snapshots_name_trgm ON venue_snapshots USING gin (name gin_trgm_ops)")

    op.create_table(
        "venue_menu_snapshots",
        _uuid_pk(),
        sa.Column("venue_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("place_id", sa.String(length=128), nullable=False),
        sa.Column("menu_item_id", sa.String(length=128), nullable=False),
        sa.Column("menu_revision", sa.String(length=128), nullable=False),
        sa.Column("beverage_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("menu_name", sa.String(length=255), nullable=False),
        sa.Column("menu_type", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["beverage_item_id"], ["beverage_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["venue_snapshot_id"], ["venue_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_venue_menu_snapshots_place_beverage", "venue_menu_snapshots", ["place_id", "beverage_item_id"])
    op.create_index("ix_venue_menu_snapshots_place_menu", "venue_menu_snapshots", ["place_id", "menu_item_id"])

    op.create_table(
        "venue_inventory_snapshots",
        _uuid_pk(),
        sa.Column("venue_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("place_id", sa.String(length=128), nullable=False),
        sa.Column("beverage_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_beverage_id", sa.String(length=128), nullable=True),
        sa.Column("inventory_revision", sa.String(length=128), nullable=False),
        sa.Column("availability_status", sa.String(length=50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["beverage_item_id"], ["beverage_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["venue_snapshot_id"], ["venue_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_venue_inventory_snapshots_lookup",
        "venue_inventory_snapshots",
        ["place_id", "beverage_item_id", "availability_status"],
    )
    op.create_index("ix_venue_inventory_snapshots_expires", "venue_inventory_snapshots", ["expires_at"])

    op.create_table(
        "venue_price_snapshots",
        _uuid_pk(),
        sa.Column("venue_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("place_id", sa.String(length=128), nullable=False),
        sa.Column("beverage_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("menu_item_id", sa.String(length=128), nullable=True),
        sa.Column("price_revision", sa.String(length=128), nullable=False),
        sa.Column("price_krw", sa.Integer(), nullable=False),
        sa.Column("price_type", sa.String(length=50), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["beverage_item_id"], ["beverage_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["venue_snapshot_id"], ["venue_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_venue_price_snapshots_place_beverage", "venue_price_snapshots", ["place_id", "beverage_item_id"])
    op.create_index("ix_venue_price_snapshots_valid_until", "venue_price_snapshots", ["valid_until"])

    op.create_table(
        "flavor_profiles",
        _uuid_pk(),
        sa.Column("owner_type", sa.String(length=50), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("flavor_tags", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("profile_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("curation_confidence", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_flavor_profiles_owner", "flavor_profiles", ["owner_type", "owner_id"])

    op.create_table(
        "recommendation_requests",
        _uuid_pk(),
        sa.Column("external_user_id", sa.String(length=128), nullable=False),
        sa.Column("profile_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("filters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scoring_config_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("request_context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["profile_revision_id"], ["taste_profile_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["scoring_config_id"], ["scoring_configs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recommendation_requests_user_created", "recommendation_requests", ["external_user_id", "created_at"])
    op.create_index("ix_recommendation_requests_profile", "recommendation_requests", ["profile_revision_id"])

    op.create_table(
        "recommendation_results",
        _uuid_pk(),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.Column("score_breakdown_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("qdrant_point_id", sa.String(length=128), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["request_id"], ["recommendation_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recommendation_results_request_rank", "recommendation_results", ["request_id", "rank"])
    op.create_index("ix_recommendation_results_target", "recommendation_results", ["target_type", "target_id"])

    op.create_table(
        "recommendation_explanations",
        _uuid_pk(),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason_codes", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("matched_dimensions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("template_version", sa.String(length=50), nullable=False),
        sa.Column("explanation_text", sa.Text(), nullable=False),
        sa.Column("debug_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["result_id"], ["recommendation_results.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recommendation_explanations_result", "recommendation_explanations", ["result_id"])

    op.create_table(
        "recommendation_interactions",
        _uuid_pk(),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["request_id"], ["recommendation_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["result_id"], ["recommendation_results.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recommendation_interactions_result_event", "recommendation_interactions", ["result_id", "event_type"])
    op.create_index("ix_recommendation_interactions_created", "recommendation_interactions", ["created_at"])

    op.create_table(
        "survey_sync_cursors",
        sa.Column("source_name", sa.String(length=100), nullable=False),
        sa.Column("cursor_value", sa.String(length=255), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("source_name"),
    )

    op.create_table(
        "survey_sync_events",
        _uuid_pk(),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("external_user_id", sa.String(length=128), nullable=False),
        sa.Column("survey_response_id", sa.String(length=128), nullable=False),
        sa.Column("survey_version", sa.String(length=100), nullable=True),
        sa.Column("response_revision", sa.Integer(), nullable=False),
        sa.Column("event_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_survey_sync_events_event_id"),
    )
    op.create_index("ix_survey_sync_events_status_retry", "survey_sync_events", ["status", "next_retry_at"])
    op.create_index("ix_survey_sync_events_survey_response", "survey_sync_events", ["survey_response_id"])

    op.create_table(
        "dead_letter_events",
        _uuid_pk(),
        sa.Column("sync_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=True),
        sa.Column("event_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dead_letter_reason", sa.Text(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["sync_event_id"], ["survey_sync_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dead_letter_events_event_id", "dead_letter_events", ["event_id"])

    op.create_table(
        "rebuild_jobs",
        _uuid_pk(),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("scope_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_by", sa.String(length=128), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rebuild_jobs_status_created", "rebuild_jobs", ["status", "created_at"])

    op.create_table(
        "rebuild_job_items",
        _uuid_pk(),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(length=100), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["job_id"], ["rebuild_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rebuild_job_items_job_status", "rebuild_job_items", ["job_id", "status"])
    op.create_index("ix_rebuild_job_items_target", "rebuild_job_items", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_index("ix_rebuild_job_items_target", table_name="rebuild_job_items")
    op.drop_index("ix_rebuild_job_items_job_status", table_name="rebuild_job_items")
    op.drop_table("rebuild_job_items")
    op.drop_index("ix_rebuild_jobs_status_created", table_name="rebuild_jobs")
    op.drop_table("rebuild_jobs")
    op.drop_index("ix_dead_letter_events_event_id", table_name="dead_letter_events")
    op.drop_table("dead_letter_events")
    op.drop_index("ix_survey_sync_events_survey_response", table_name="survey_sync_events")
    op.drop_index("ix_survey_sync_events_status_retry", table_name="survey_sync_events")
    op.drop_table("survey_sync_events")
    op.drop_table("survey_sync_cursors")
    op.drop_index("ix_recommendation_interactions_created", table_name="recommendation_interactions")
    op.drop_index("ix_recommendation_interactions_result_event", table_name="recommendation_interactions")
    op.drop_table("recommendation_interactions")
    op.drop_index("ix_recommendation_explanations_result", table_name="recommendation_explanations")
    op.drop_table("recommendation_explanations")
    op.drop_index("ix_recommendation_results_target", table_name="recommendation_results")
    op.drop_index("ix_recommendation_results_request_rank", table_name="recommendation_results")
    op.drop_table("recommendation_results")
    op.drop_index("ix_recommendation_requests_profile", table_name="recommendation_requests")
    op.drop_index("ix_recommendation_requests_user_created", table_name="recommendation_requests")
    op.drop_table("recommendation_requests")
    op.drop_index("ix_flavor_profiles_owner", table_name="flavor_profiles")
    op.drop_table("flavor_profiles")
    op.drop_index("ix_venue_price_snapshots_valid_until", table_name="venue_price_snapshots")
    op.drop_index("ix_venue_price_snapshots_place_beverage", table_name="venue_price_snapshots")
    op.drop_table("venue_price_snapshots")
    op.drop_index("ix_venue_inventory_snapshots_expires", table_name="venue_inventory_snapshots")
    op.drop_index("ix_venue_inventory_snapshots_lookup", table_name="venue_inventory_snapshots")
    op.drop_table("venue_inventory_snapshots")
    op.drop_index("ix_venue_menu_snapshots_place_menu", table_name="venue_menu_snapshots")
    op.drop_index("ix_venue_menu_snapshots_place_beverage", table_name="venue_menu_snapshots")
    op.drop_table("venue_menu_snapshots")
    op.execute("DROP INDEX IF EXISTS ix_venue_snapshots_name_trgm")
    op.drop_index("ix_venue_snapshots_search_document", table_name="venue_snapshots")
    op.drop_index("ix_venue_snapshots_location", table_name="venue_snapshots")
    op.drop_index("ix_venue_snapshots_status_stale", table_name="venue_snapshots")
    op.drop_index("ix_venue_snapshots_place_revision", table_name="venue_snapshots")
    op.drop_table("venue_snapshots")
    op.execute("DROP INDEX IF EXISTS ix_beverage_items_name_en_trgm")
    op.execute("DROP INDEX IF EXISTS ix_beverage_items_name_ko_trgm")
    op.drop_index("ix_beverage_items_search_document", table_name="beverage_items")
    op.drop_index("ix_beverage_items_price_range", table_name="beverage_items")
    op.drop_index("ix_beverage_items_category_active", table_name="beverage_items")
    op.drop_table("beverage_items")
    op.drop_index("ix_qdrant_points_vector_id", table_name="qdrant_points")
    op.drop_table("qdrant_points")
    op.drop_index("ix_recommendation_vectors_owner", table_name="recommendation_vectors")
    op.drop_table("recommendation_vectors")
    op.drop_table("survey_source_snapshots")
    op.drop_index("ix_taste_profile_revisions_survey_mapper", table_name="taste_profile_revisions")
    op.drop_index("ix_taste_profile_revisions_user_revision", table_name="taste_profile_revisions")
    op.drop_constraint("fk_user_profile_state_active_profile_revision", "user_profile_state", type_="foreignkey")
    op.drop_table("taste_profile_revisions")
    op.drop_table("user_profile_state")
    op.drop_table("scoring_configs")
    op.drop_table("mapper_versions")
    op.drop_table("vector_schema_versions")
