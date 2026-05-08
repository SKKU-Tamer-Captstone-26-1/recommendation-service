# ERD and Storage Model

## Purpose

This document defines the canonical PostgreSQL storage model and Qdrant indexing
metadata for `recommendation-service`.

## Document Contract

### Why This File Exists

- Makes recommendation-owned state explicit.
- Keeps PostgreSQL canonical and Qdrant rebuildable.
- Provides a stable target for migrations and AI-assisted implementation.

### What MUST Be Documented Here

- Tables owned by `recommendation-service`.
- Important columns and relationships.
- Canonical vs derived/indexed state.
- Qdrant metadata tables.
- Important indexes and partitioning rules.
- Rebuild and audit relevance.

### What MUST NOT Be Documented Here

- Raw survey-service tables.
- Auth-service user tables.
- Full SQL migration code.
- Recommendation scoring formulas.

### Recommended Sections

1. Purpose
2. Storage Principles
3. ERD
4. Table Definitions
5. Important Indexes
6. Partitioning
7. Qdrant Collection Metadata
8. Update Rules

### Engineering Constraints

- PostgreSQL MUST be canonical for all recommendation-owned state.
- Qdrant point metadata MUST be rebuildable from PostgreSQL vectors.
- Tables storing versioned artifacts SHOULD be append-only after activation.
- Recommendation events SHOULD be partitioned by time.
- Venue location search SHOULD use PostGIS.

### Update Rules

- Update before or with any schema migration.
- Every table change must include ownership, lifecycle, and rebuild impact.
- Do not document survey-service or auth-service private schemas here.

## Storage Principles

Canonical recommendation-owned state:

- profile revisions
- survey source identifiers and generation snapshots
- vector schema versions
- mapper versions
- recommendation vectors
- scoring configs
- catalog data curated by recommendation-service
- recommendation request/result/explanation logs
- sync cursors and failure state

Derived rebuildable state:

- Qdrant collections
- Qdrant point payloads

## ERD

```mermaid
erDiagram
    user_profile_state ||--o{ taste_profile_revisions : has
    taste_profile_revisions ||--|| survey_source_snapshots : generated_from
    taste_profile_revisions ||--o{ recommendation_vectors : owns
    vector_schema_versions ||--o{ recommendation_vectors : defines
    mapper_versions ||--o{ taste_profile_revisions : generates
    scoring_configs ||--o{ recommendation_requests : scores
    recommendation_vectors ||--o{ qdrant_points : indexed_as

    beverage_items ||--o{ flavor_profiles : has
    venues ||--o{ venue_menu_items : has
    venue_menu_items ||--o{ flavor_profiles : has
    flavor_profiles ||--o{ recommendation_vectors : produces

    recommendation_requests ||--o{ recommendation_results : returns
    recommendation_results ||--o{ recommendation_explanations : explains
    recommendation_results ||--o{ recommendation_interactions : receives

    survey_sync_cursors ||--o{ survey_sync_events : advances
    survey_sync_events ||--o{ dead_letter_events : may_fail
    rebuild_jobs ||--o{ rebuild_job_items : contains
```

## Table Definitions

### `user_profile_state`

One row per external user with current profile status.

Key fields:

- `external_user_id`
- `active_profile_revision_id`
- `status`
- `last_survey_response_id`
- `updated_at`

### `taste_profile_revisions`

Immutable derived profile revisions.

Key fields:

- `id`
- `external_user_id`
- `profile_revision`
- `survey_response_id`
- `survey_version`
- `survey_response_revision`
- `mapper_version_id`
- `vector_schema_version_id`
- `scoring_config_id`
- `taste_vector`
- `preferred_categories`
- `preferred_keywords`
- `budget_range`
- `experience_level`
- `status`
- `generated_at`

### `survey_source_snapshots`

Generation snapshot metadata. Not raw survey source of truth.

Key fields:

- `profile_revision_id`
- `survey_response_id`
- `snapshot_hash`
- `snapshot_json`
- `fetched_at`

### `vector_schema_versions`

Version registry for vector dimensions and metrics.

Key fields:

- `name`
- `version`
- `dimensions_json`
- `distance_metric`
- `status`

### `mapper_versions`

Version registry for survey-to-profile mapping.

Key fields:

- `name`
- `version`
- `code_hash`
- `rules_json`
- `status`

### `scoring_configs`

Versioned recommendation scoring metadata.

Key fields:

- `name`
- `version`
- `target_type`
- `category`
- `weights_json`
- `reason_code_rules_json`
- `status`

### `recommendation_vectors`

Canonical vector storage.

Key fields:

- `owner_type`
- `owner_id`
- `vector_schema_version_id`
- `vector`
- `vector_json`
- `confidence_json`
- `source_hash`
- `created_at`

### `qdrant_points`

Qdrant indexing metadata.

Key fields:

- `vector_id`
- `collection_name`
- `point_id`
- `payload_hash`
- `index_status`
- `indexed_at`
- `last_error`

### `beverage_items`

Curated beverage catalog.

Key fields:

- `category`
- `name_ko`
- `name_en`
- `brand`
- `country`
- `region`
- `abv`
- `price_min_krw`
- `price_max_krw`
- `active`
- `search_document`

### `venues`

Bars, bottle shops, and experience locations.

Key fields:

- `name`
- `type`
- `address`
- `location geography(Point, 4326)`
- `price_level`
- `active`
- `search_document`

### `recommendation_requests`

Request-level recommendation log.

Key fields:

- `external_user_id`
- `profile_revision_id`
- `target_type`
- `filters_json`
- `scoring_config_id`
- `created_at`

### `recommendation_results`

Ranked result log.

Key fields:

- `request_id`
- `rank`
- `target_type`
- `target_id`
- `similarity_score`
- `final_score`
- `score_breakdown_json`

### `recommendation_explanations`

Deterministic explanation payload.

Key fields:

- `result_id`
- `reason_codes`
- `matched_dimensions_json`
- `template_version`
- `explanation_text`
- `debug_json`

### `survey_sync_events`

Idempotent survey event processing state.

Key fields:

- `event_id`
- `event_type`
- `external_user_id`
- `survey_response_id`
- `response_revision`
- `status`
- `attempt_count`
- `next_retry_at`
- `last_error`

## Important Indexes

Required indexes:

```text
user_profile_state(external_user_id)
taste_profile_revisions(external_user_id, profile_revision desc)
taste_profile_revisions(survey_response_id, survey_response_revision, mapper_version_id)
recommendation_vectors(owner_type, owner_id, vector_schema_version_id)
qdrant_points(collection_name, point_id)
beverage_items(category, active)
venues using gist(location)
survey_sync_events(event_id)
survey_sync_events(status, next_retry_at)
recommendation_results(request_id, rank)
```

Hybrid search indexes:

```text
beverage_items.search_document using gin
venues.search_document using gin
trigram index on searchable Korean/English names
```

## Partitioning

Partition by month:

- `recommendation_requests`
- `recommendation_results`
- `recommendation_interactions`

Partitioning can be implemented after MVP traffic is known, but table design
SHOULD avoid blocking future partitioning.

## Qdrant Collections

Recommended collections:

```text
beverage_vectors_v1
venue_vectors_v1
menu_item_vectors_v1
```

Qdrant payloads SHOULD include only filterable metadata:

```json
{
  "owner_id": "bev_123",
  "category": "whiskey",
  "active": true,
  "vector_schema_version": "taste_v1",
  "source_hash": "sha256..."
}
```

