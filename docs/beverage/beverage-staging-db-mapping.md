# Beverage Staging DB Mapping

## Purpose

This document maps the conceptual beverage collection staging tables requested by
the first beverage data collector task to the current repository state.

No staging tables or DB-writing importer were found in this repository at
collection time.

A local dry-run validator now exists:

```bash
python3 -m app.tools.beverage_candidate_dry_run \
  --data-dir data/beverage \
  --report reports/beverage-dry-run-2026-05-23.md
```

The dry-run validator reads candidate files, checks source registry coverage,
validates candidate shape, detects duplicates, checks catalog/flavor/knowledge
linkage, and verifies Korea/KRW price observations. It writes only a Markdown
report and does not write canonical tables, staging tables, or Qdrant.

## Repository Inspection Result

Inspected areas:

- `migrations/versions/0001_initial_foundation.py`
- `app/models/`
- `app/repositories/`
- `scripts/`
- `prompts/beverage/`
- `data/beverage/`
- `app/tools/beverage_candidate_dry_run.py`

Found canonical recommendation-owned tables:

- `beverage_items`
- `flavor_profiles`
- `recommendation_vectors`
- `vector_schema_versions`
- `scoring_configs`
- `qdrant_points`

Found no staging equivalents for:

- `recommendation_staging.beverage_collection_runs`
- `recommendation_staging.beverage_catalog_candidates`
- `recommendation_staging.beverage_flavor_profile_candidates`
- `recommendation_staging.beverage_knowledge_candidates`
- `recommendation_staging.beverage_price_observation_candidates`
- `recommendation_staging.beverage_source_refs`

Found candidate validation tooling:

- `app.tools.beverage_candidate_dry_run`

## Mapping

| Conceptual staging table | Current actual table | Current action |
|---|---|---|
| `recommendation_staging.beverage_collection_runs` | none | Create staging schema in follow-up task |
| `recommendation_staging.beverage_catalog_candidates` | none | Keep candidate records in `data/beverage/catalog_candidates.jsonl` |
| `recommendation_staging.beverage_flavor_profile_candidates` | none | Keep candidate records in `data/beverage/flavor_profile_candidates.jsonl` |
| `recommendation_staging.beverage_knowledge_candidates` | none | Keep candidate records in `data/beverage/knowledge_candidates.jsonl` |
| `recommendation_staging.beverage_price_observation_candidates` | none | Keep candidate records in `data/beverage/price_observation_candidates.jsonl` |
| `recommendation_staging.beverage_source_refs` | none | Keep source registry in `data/beverage/source_registry.csv` |

## Canonical Table Non-Write Decision

The first batch was not inserted into canonical tables.

Reason:

- Candidate records are not human-reviewed.
- No staging schema exists.
- Dry-run validation exists, but it does not import to DB.
- The task explicitly forbids canonical beverage writes when staging is missing.

## Desired Staging Behavior

The follow-up staging implementation should support:

- ingesting JSONL/CSV candidate files into `recommendation_staging`
- validating schema shape before insert
- rejecting `approved` status from automated imports
- preserving source URLs and retrieved dates
- storing raw candidate JSON for reproducibility
- using the dry-run report before any staging write
- never writing canonical `beverage_items`, `flavor_profiles`, or
  `recommendation_vectors`

## Dry-Run Report Status

The first dry-run report was generated at:

```text
reports/beverage-dry-run-2026-05-23.md
```

Current result after the May 23, 2026 Korea/KRW cleanup and follow-up KRW price
collection:

- accepted rows: 671
- warning rows: 0
- rejected rows: 0

The legacy non-KRW price rows are preserved in
`data/beverage/price_observation_legacy_non_kr_candidates.jsonl` and are no
longer part of the Korea/KRW dry-run path.

## Follow-Up Prompt

The staging schema implementation prompt was created at:

```text
prompts/beverage/create-beverage-staging-schema.md
```
