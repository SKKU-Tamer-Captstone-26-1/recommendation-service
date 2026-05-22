# Beverage Staging DB Mapping

## Purpose

This document maps the conceptual beverage collection staging tables requested by
the first beverage data collector task to the current repository state.

No staging tables or safe importer were found in this repository at collection
time.

## Repository Inspection Result

Inspected areas:

- `migrations/versions/0001_initial_foundation.py`
- `app/models/`
- `app/repositories/`
- `scripts/`
- `prompts/beverage/`
- `data/beverage/`

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
- No dry-run staging importer exists.
- The task explicitly forbids canonical beverage writes when staging is missing.

## Desired Staging Behavior

The follow-up staging implementation should support:

- ingesting JSONL/CSV candidate files into `recommendation_staging`
- validating schema shape before insert
- rejecting `approved` status from automated imports
- preserving source URLs and retrieved dates
- storing raw candidate JSON for reproducibility
- producing a dry-run report before any staging write
- never writing canonical `beverage_items`, `flavor_profiles`, or
  `recommendation_vectors`

## Follow-Up Prompt

The staging schema implementation prompt was created at:

```text
prompts/beverage/create-beverage-staging-schema.md
```
