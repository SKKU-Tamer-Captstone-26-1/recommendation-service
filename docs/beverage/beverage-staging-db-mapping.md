# Beverage Staging DB Mapping

## Purpose

This document maps the conceptual beverage collection staging tables requested by
the first beverage data collector task to the current repository state.

Staging tables and a DB-writing importer now exist for review-only candidate
loading. The importer writes to `recommendation_staging` first and promotes only
the fixed MVP seed subset into canonical beverage catalog/vector tables.

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

Found staging equivalents for:

- `recommendation_staging.beverage_collection_runs`
- `recommendation_staging.beverage_catalog_candidates`
- `recommendation_staging.beverage_flavor_profile_candidates`
- `recommendation_staging.beverage_knowledge_candidates`
- `recommendation_staging.beverage_price_observation_candidates`
- `recommendation_staging.beverage_source_refs`
- `recommendation_staging.beverage_candidate_import_errors`

Found candidate validation tooling:

- `app.tools.beverage_candidate_dry_run`

## Mapping

| Conceptual staging table | Current actual table | Current action |
|---|---|---|
| `recommendation_staging.beverage_collection_runs` | implemented | Store run manifest and import status |
| `recommendation_staging.beverage_catalog_candidates` | implemented | Store catalog candidate raw JSON |
| `recommendation_staging.beverage_flavor_profile_candidates` | implemented | Store flavor candidate raw JSON |
| `recommendation_staging.beverage_knowledge_candidates` | implemented | Store knowledge candidate raw JSON |
| `recommendation_staging.beverage_price_observation_candidates` | implemented | Store KRW price observation raw JSON |
| `recommendation_staging.beverage_source_refs` | implemented | Store source registry rows |

## Canonical Table Promotion Decision

The full candidate batch must not be inserted into canonical beverage identity,
flavor, or vector tables.

Reason:

- Most candidate records are not human-reviewed.
- The dry-run validator only proves shape/linkage, not curation approval.
- Only the fixed MVP seed subset from `docs/plans/002.md` is eligible for
  canonical promotion.
- Human-verified KR/KRW price observations for promoted seed beverages may be
  copied into `beverage_items.price_min_krw`, `beverage_items.price_max_krw`,
  and `metadata_json.price_observations`.
- Candidate price observations are broad catalog evidence only. They are not
  live venue price truth, inventory truth, or strict budget-filter evidence.

## Current Staging Behavior

The staging importer supports:

- ingesting JSONL/CSV candidate files into `recommendation_staging`
- validating schema shape before insert
- rejecting `approved` status from automated imports
- preserving source URLs and retrieved dates
- storing raw candidate JSON for reproducibility
- using the dry-run report before any staging write
- promoting only the fixed reviewed MVP seed subset into canonical
  `beverage_items`, `flavor_profiles`, and `recommendation_vectors`
- promoting human-verified KRW price observations for that fixed subset into
  canonical beverage item price range fields and traceable metadata

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
