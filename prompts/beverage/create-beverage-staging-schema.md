# Task: Create Beverage Candidate Staging Schema

You are Codex working in `/Users/jeonghun/recommendation-service`.

Follow:

```text
AGENTS.md
.agent/HARNESS.md
docs/recommendation/beverage-catalog.md
docs/database/erd.md
docs/database/migration-strategy.md
docs/beverage/beverage-staging-db-mapping.md
```

## Goal

Create a local/dev staging schema for beverage collection candidates so the
beverage data collector can dry-run and then insert candidate records without
writing canonical beverage tables.

This is a staging implementation task, not canonical beverage approval.

## Hard Rules

Do not:

```text
- write production DB
- write canonical beverage records
- mark records approved
- mutate map/admin/auth/survey DBs
- create cross-service foreign keys
- create Qdrant points
- implement recommendation ranking
```

Allowed:

```text
- additive Alembic migration for recommendation-owned staging schema
- local/dev dry-run importer
- staging-only apply command
- validation tests
- documentation updates under docs/beverage/
```

## Expected Staging Tables

Create these tables unless an existing reviewed naming convention requires a
different prefix:

```text
recommendation_staging.beverage_collection_runs
recommendation_staging.beverage_catalog_candidates
recommendation_staging.beverage_flavor_profile_candidates
recommendation_staging.beverage_knowledge_candidates
recommendation_staging.beverage_price_observation_candidates
recommendation_staging.beverage_source_refs
```

## Minimum Table Requirements

Every staging candidate table should include:

```text
id
run_id
candidate_id or observation_id
candidate_status
source_urls or source_ref_ids
raw_candidate_json
validation_status
validation_errors_json
created_at
updated_at
```

Rules:

- Reject `approved` from automated imports.
- Preserve raw candidate JSON for auditability.
- Add uniqueness constraints for candidate IDs within a run.
- Add indexes on `run_id`, `candidate_status`, and normalized names where useful.
- Keep staging tables independent from canonical `beverage_items`.
- Do not add foreign keys to map/admin/auth/survey service tables.

## Importer Requirements

Add a command or script that supports:

```text
--dry-run
--apply-staging
--input-dir data/beverage
--run-id <run_id>
```

Dry-run must:

- parse all JSONL and CSV files
- validate required fields
- validate candidate IDs are unique
- validate flavor vectors are 0.0 to 1.0
- validate every flavor candidate references a catalog candidate
- validate every knowledge candidate references a catalog candidate
- validate every price observation references a catalog candidate
- report counts and errors
- write nothing

Apply-staging must:

- run the same validation first
- insert only into `recommendation_staging`
- be idempotent by `run_id` and candidate ID
- report inserted, updated, skipped, and rejected counts

## Tests

Add focused tests for:

- JSONL validation success
- duplicate candidate ID rejection
- invalid vector value rejection
- missing catalog reference rejection
- dry-run writes nothing
- apply-staging idempotency
- `approved` status rejection

## Acceptance Criteria

- Alembic migration creates only `recommendation_staging` tables.
- No canonical beverage table is written by tests or importer.
- `data/beverage/` first batch can be dry-run successfully.
- Apply mode is clearly local/dev staging only.
- Verification commands and results are documented in the final response.
