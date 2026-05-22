# Migration Strategy

## Purpose

This document defines how database, vector, mapper, and scoring changes are
introduced safely.

## Document Contract

### Why This File Exists

- Keeps schema evolution compatible with rebuildability.
- Prevents silent vector or mapper changes.
- Gives backend and AI contributors a safe migration checklist.

### What MUST Be Documented Here

- Migration principles.
- Alembic expectations.
- Backfill rules.
- Vector/schema version migration rules.
- Rollback and recovery expectations.
- Documentation update requirements.

### What MUST NOT Be Documented Here

- Full migration SQL.
- Current table definitions. Use `erd.md`.
- Recommendation formulas.
- Deployment runbooks unrelated to schema changes.

### Recommended Sections

1. Purpose
2. Migration Principles
3. Schema Migration Template
4. Backfill Rules
5. Vector and Mapper Migration Rules
6. Rollback Rules
7. Documentation Requirements
8. Update Rules

### Engineering Constraints

- Migrations MUST preserve existing profile revisions unless explicitly archived.
- Vector semantic changes MUST create a new vector schema version.
- Mapper behavior changes MUST create a new mapper version.
- Scoring behavior changes MUST create a new scoring config version.
- Qdrant migrations MUST be rebuildable from PostgreSQL.

### Update Rules

- Update when migration tooling, schema compatibility policy, or rebuild policy
  changes.
- Keep this document focused on process needed for correctness.

## Migration Principles

- Prefer additive migrations.
- Keep destructive migrations rare and explicitly reviewed.
- Separate schema migration from large data backfills when practical.
- Write migrations so deployed old and new code can coexist during rollout when
  possible.
- Every migration touching rebuildable state must define rebuild impact.
- Before the first production migration, confirm `implementation-readiness.md`
  database gate and ERD ownership boundaries.

## Schema Migration Template

Each migration should document:

```text
Title:
Reason:
Affected tables:
Affected docs:
Backward compatibility:
Backfill required:
Rollback strategy:
Rebuild impact:
Qdrant impact:
Operational risk:
```

## Backfill Rules

Backfills MUST be idempotent.

Backfills SHOULD:

- operate in batches
- persist progress
- be restartable
- log counts and failures
- avoid holding long locks

## Beverage Catalog Migration Rules

The beverage catalog foundation should be PostgreSQL-first.

Current foundation tables are sufficient to begin MVP catalog work:

- `beverage_items`
- `flavor_profiles`
- `recommendation_vectors`
- `vector_schema_versions`
- `scoring_configs`
- `qdrant_points`

If the initial migration has not been deployed outside local development, keep
the catalog foundation in the initial migration and add seed/import code
separately.

If the initial migration has already been applied, do not rewrite it. Use
additive migrations only.

Seed data rules:

- Store 10-20 MVP beverage seed records in a versioned JSON file.
- Use deterministic UUIDs.
- Store `catalog_key` in `metadata_json` unless a future migration promotes it
  to a real column.
- Import idempotently into `beverage_items`, `flavor_profiles`, and
  `recommendation_vectors`.
- Validate every seed vector against `taste_v1` before writing.
- Do not create Qdrant points as part of initial catalog seed unless the indexing
  worker is explicitly implemented.

Optional future migration:

```text
0002_add_beverage_catalog_key
- add beverage_items.catalog_key nullable
- backfill from metadata_json.catalog_key
- add a unique index
- set NOT NULL after validation
```

Do not add this migration until catalog admin/search workflows need a database
level natural key.

## Vector and Mapper Migration Rules

Create a new vector schema version for:

- dimension order changes
- dimension meaning changes
- new dimensions
- distance metric changes

Create a new mapper version for:

- survey answer weight changes
- survey input shape changes
- keyword mapping changes
- output profile logic changes

Create a new scoring config version for:

- ranking weight changes
- reason code rule changes
- diversity/exploration changes
- category-specific scoring changes

## Qdrant Migration Rules

Qdrant collections are derived and rebuildable.

Allowed:

- recreate collection from PostgreSQL vectors
- add new collection for new vector schema
- reindex failed or stale points

Forbidden:

- relying on Qdrant as the only vector store
- manually changing Qdrant payload semantics without PostgreSQL metadata update

## Rollback Rules

Rollback strategy MUST be documented before running production migrations.

Acceptable rollback patterns:

- disable new code path with config
- switch active scoring config back to previous version
- switch active vector schema usage back to previous version
- restore Qdrant from PostgreSQL vectors

Destructive rollback from backup should be last resort.

## Documentation Requirements

Update docs before or with migrations affecting:

- service ownership
- table structure
- vector schema
- mapper logic
- scoring config
- sync events
- API contracts
- rebuild/recovery behavior

Do not create migrations for map-service/place-service canonical tables in this
repository. Only create recommendation-owned tables and map/place read-model
snapshot tables.
