"""selected beverage venue recommendations

Revision ID: 0003_venue_recs
Revises: 0002_beverage_engine
Create Date: 2026-05-23

Title: selected beverage venue recommendations
Reason: Add map/place snapshot sync state and venue recommendation source
snapshot metadata required for reproducible selected-beverage venue ranking.
Affected tables: map_snapshot_sync_cursors, map_snapshot_sync_events,
recommendation_results, venue_*_snapshots indexes.
Affected docs: docs/plans/003.md, docs/database/erd.md,
docs/api/recommendation-api.md, docs/recommendation/map-read-model.md.
Backward compatibility: additive only.
Backfill required: existing recommendation_results receive {} metadata.
Rollback strategy: drop additive sync tables, unique read-model indexes, and
source_snapshot_json if no venue result rows depend on it.
Rebuild impact: map/place read models remain rebuildable from approved
snapshot/event inputs.
Qdrant impact: none.
Operational risk: medium; venue ranking depends on snapshot freshness and
confidence, but canonical map/place data remains untouched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0003_venue_recs"
down_revision: str | None = "0002_beverage_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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


def upgrade() -> None:
    op.add_column(
        "recommendation_results",
        sa.Column(
            "source_snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )

    op.create_table(
        "map_snapshot_sync_cursors",
        sa.Column("source_name", sa.String(length=100), nullable=False),
        sa.Column("cursor_value", sa.String(length=255), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        *_timestamps(),
        sa.PrimaryKeyConstraint("source_name"),
    )

    op.create_table(
        "map_snapshot_sync_events",
        _uuid_pk(),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("place_id", sa.String(length=128), nullable=False),
        sa.Column("place_revision", sa.String(length=128), nullable=True),
        sa.Column("menu_revision", sa.String(length=128), nullable=True),
        sa.Column("inventory_revision", sa.String(length=128), nullable=True),
        sa.Column("price_revision", sa.String(length=128), nullable=True),
        sa.Column(
            "event_payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_map_snapshot_sync_events_event_id"),
    )
    op.create_index(
        "ix_map_snapshot_sync_events_status_retry",
        "map_snapshot_sync_events",
        ["status", "next_retry_at"],
    )
    op.create_index(
        "ix_map_snapshot_sync_events_place",
        "map_snapshot_sync_events",
        ["place_id"],
    )

    op.create_unique_constraint(
        "uq_venue_snapshots_place_revision",
        "venue_snapshots",
        ["place_id", "place_revision"],
    )
    op.create_unique_constraint(
        "uq_venue_menu_snapshots_identity",
        "venue_menu_snapshots",
        ["place_id", "menu_item_id", "menu_revision"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_venue_inventory_snapshots_identity
        ON venue_inventory_snapshots (
            place_id,
            COALESCE(beverage_item_id::text, ''),
            COALESCE(source_beverage_id, ''),
            inventory_revision
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_venue_price_snapshots_identity
        ON venue_price_snapshots (
            place_id,
            COALESCE(beverage_item_id::text, ''),
            COALESCE(menu_item_id, ''),
            price_revision
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_venue_price_snapshots_identity")
    op.execute("DROP INDEX IF EXISTS uq_venue_inventory_snapshots_identity")
    op.drop_constraint(
        "uq_venue_menu_snapshots_identity",
        "venue_menu_snapshots",
        type_="unique",
    )
    op.drop_constraint(
        "uq_venue_snapshots_place_revision",
        "venue_snapshots",
        type_="unique",
    )
    op.drop_index(
        "ix_map_snapshot_sync_events_place",
        table_name="map_snapshot_sync_events",
    )
    op.drop_index(
        "ix_map_snapshot_sync_events_status_retry",
        table_name="map_snapshot_sync_events",
    )
    op.drop_table("map_snapshot_sync_events")
    op.drop_table("map_snapshot_sync_cursors")
    op.drop_column("recommendation_results", "source_snapshot_json")
