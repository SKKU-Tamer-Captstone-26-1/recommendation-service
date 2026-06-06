# Beverage Catalog Foundation

## Purpose

This document defines the minimum beverage catalog foundation required before
beverage recommendations or real Qdrant indexing are implemented.

The catalog must give `recommendation-service` enough PostgreSQL-owned data to
store curated beverages, explainable taste profiles, canonical beverage vectors,
and reason-code metadata.

## Core Rule

Build the PostgreSQL beverage catalog before real Qdrant indexing.

Qdrant has no useful role until PostgreSQL contains:

- active beverage catalog rows
- curated beverage taste profiles
- canonical beverage vectors
- vector schema version references
- source hashes and confidence metadata

Qdrant remains a rebuildable derived index. It MUST NOT become the canonical
source of beverage identity, flavor metadata, or vectors.

## Ownership Boundary

`recommendation-service` MAY own a curated MVP beverage catalog for recommendation
purposes.

It owns:

- beverage catalog records used by recommendations
- beverage taste profile metadata
- canonical beverage vectors
- beverage recommendation reason-code hints
- catalog seed/import metadata

It does not own:

- map-service venue inventory truth
- map-service menu truth
- map-service price truth
- raw survey answers
- authentication or user identity

Venue/menu/inventory/price records may reference `beverage_items`, but canonical
availability and price remain owned by map-service/place-service.

## MVP Storage Contract

Use the existing foundation tables for MVP.

| Table | Role | Canonical? |
|---|---|---|
| `beverage_items` | Curated beverage identity, category, display fields, price range, active flag | Yes, for recommendation-owned catalog |
| `flavor_profiles` | Curated taste profile and reason-code hints for a beverage | Yes, for recommendation-owned curation metadata |
| `recommendation_vectors` | Canonical beverage vector in `taste_v1` | Yes |
| `vector_schema_versions` | Versioned vector dimension contract | Yes |
| `scoring_configs` | Versioned scoring and reason-code rule metadata | Yes |
| `qdrant_points` | Future derived index metadata for vectors | No, rebuildable |

The MVP does not need a separate beverage catalog service.

## `beverage_items`

Purpose:

- Store the recommendation-owned beverage catalog item.
- Provide stable fields for display, filtering, search, and seed/import.

Required MVP fields:

| Field | Rule |
|---|---|
| `id` | Stable UUID. Seed data SHOULD use deterministic UUIDs. |
| `category` | Required. Examples: `whiskey`, `wine`, `beer`, `cocktail`, `soju`, `sake`, `liqueur`. |
| `name_ko` | Required display name. |
| `name_en` | Optional English display name. |
| `brand` | Optional. |
| `country` / `region` | Optional provenance filters. |
| `abv` | Optional alcohol percentage. |
| `price_min_krw` / `price_max_krw` | Optional broad expected KR retail range from human-verified beverage price observations. Not venue price truth. |
| `active` | Required serving flag. `false` excludes from recommendation candidates. |
| `description` | Optional curated description. |
| `metadata_json` | Required structured catalog metadata. |

Recommended `metadata_json` keys:

```json
{
  "catalog_key": "whiskey.buffalo_trace.bourbon",
  "style": "bourbon",
  "source_type": "operator_curated",
  "source_version": "seed_beverages_v1",
  "curation_status": "approved",
  "tags": ["bourbon", "vanilla", "caramel", "oak"],
  "serving_context": ["neat", "highball"],
  "reason_code_hints": ["MATCHES_VANILLA_CARAMEL", "BEGINNER_FRIENDLY"],
  "price_policy": "verified_krw_observations_not_live_truth",
  "price_observation_summary": {
    "market_region": "KR",
    "currency": "KRW",
    "observation_count": 1,
    "price_min_krw": 39000,
    "price_max_krw": 39000
  }
}
```

For MVP, `active` is enough for active/inactive serving state. Add a richer
status column later only when the product needs draft/review/archive workflow.

`price_min_krw` and `price_max_krw` are allowed only as broad catalog price
evidence after human review. They are useful for display, explanation, and weak
budget context, but they MUST NOT be presented as a live offer, venue menu
price, inventory truth, or strict budget-filter source. Live venue/menu prices
remain owned by map-service/place-service snapshots.

## Beverage Taste Profile

Store curated beverage flavor metadata in `flavor_profiles`.

Required MVP row:

```text
owner_type = beverage_item
owner_id = beverage_items.id
```

Required `profile_json` keys:

```json
{
  "vector_schema": "taste_v1",
  "dimension_values": {
    "sweet": 0.75,
    "fruity": 0.15,
    "dried_fruit": 0.25,
    "woody": 0.65,
    "smoky": 0.10,
    "nutty": 0.35,
    "floral": 0.05,
    "spicy": 0.35,
    "herbal": 0.05,
    "body": 0.70,
    "acidity": 0.10,
    "carbonation": 0.00,
    "alcohol_intensity": 0.60,
    "bitterness": 0.10,
    "tannin": 0.25,
    "roasted": 0.20
  },
  "dimension_confidence": {
    "sweet": 0.80,
    "woody": 0.80,
    "body": 0.70
  },
  "reason_code_hints": [
    "MATCHES_VANILLA_CARAMEL",
    "BEGINNER_FRIENDLY"
  ],
  "curation_notes": "Operator-curated seed profile."
}
```

Rules:

- `dimension_values` MUST follow `taste_v1` names and semantics.
- Unknown or weakly curated traits MUST be represented with low confidence, not
  silent zero semantics.
- Flavor profiles may be edited by operator tooling later, but edits MUST produce
  a new canonical vector row through a deterministic regeneration step.

## Canonical Beverage Vector

Store the canonical vector in `recommendation_vectors`.

Required MVP row:

```text
owner_type = beverage_item
owner_id = beverage_items.id
vector_schema_version_id = vector_schema_versions.id for taste_v1
```

Rules:

- `vector` MUST contain exactly 16 values for `taste_v1`.
- `vector_json` MUST preserve named dimension values for debugging.
- `confidence_json` MUST preserve named dimension confidence.
- `source_hash` MUST be derived from the beverage item, flavor profile, vector
  schema version, and seed/import version.
- `source_metadata_json` MUST include catalog source and reason-code basis.
- Updating taste semantics MUST create a new `vector_schema_version`.
- Updating curation or mapping behavior MUST create a new vector row with a new
  `source_hash`.

Qdrant indexing later reads from these rows. It must never be the only storage
for beverage vectors.

## Reason-Code Metadata

Reason-code metadata for beverages has two layers:

| Layer | Storage | Meaning |
|---|---|---|
| Candidate hints | `beverage_items.metadata_json.reason_code_hints` and `flavor_profiles.profile_json.reason_code_hints` | Curated reasons that may apply if score components support them |
| Scoring rules | `scoring_configs.reason_code_rules_json` | Versioned rules that decide which reasons are emitted |

Reason-code hints MUST NOT bypass scoring. A reason code should appear in a
recommendation only when the score breakdown supports it.

## Seed Data Format

MVP seed data SHOULD start with 10-20 beverages covering the main initial
categories and vector dimensions. Beta-readiness expansion SHOULD grow the
active reviewed seed to 50-75 beverages after catalog audit and evaluation
coverage exist.

Recommended seed location:

```text
scripts/seed-data/beverages.v1.json
```

Recommended shape:

```json
[
  {
    "id": "11111111-1111-4111-8111-111111111111",
    "catalog_key": "whiskey.example_bourbon",
    "category": "whiskey",
    "name_ko": "Example Bourbon",
    "name_en": "Example Bourbon",
    "brand": "Example Distillery",
    "country": "US",
    "region": "Kentucky",
    "abv": 45.0,
    "price_min_krw": 45000,
    "price_max_krw": 90000,
    "active": true,
    "description": "Sweet oak, vanilla, caramel, and medium body.",
    "style": "bourbon",
    "tags": ["vanilla", "caramel", "oak", "medium_body"],
    "flavor_tags": ["sweet", "woody", "spicy", "body"],
    "dimension_values": {
      "sweet": 0.75,
      "fruity": 0.15,
      "dried_fruit": 0.25,
      "woody": 0.65,
      "smoky": 0.10,
      "nutty": 0.35,
      "floral": 0.05,
      "spicy": 0.35,
      "herbal": 0.05,
      "body": 0.70,
      "acidity": 0.10,
      "carbonation": 0.00,
      "alcohol_intensity": 0.60,
      "bitterness": 0.10,
      "tannin": 0.25,
      "roasted": 0.20
    },
    "dimension_confidence": {
      "sweet": 0.80,
      "woody": 0.80,
      "body": 0.70
    },
    "reason_code_hints": [
      "MATCHES_VANILLA_CARAMEL",
      "BEGINNER_FRIENDLY"
    ]
  }
]
```

Initial seed set SHOULD cover:

- 3-4 whiskeys
- 2-3 wines
- 2-3 beers
- 2-3 cocktails or cocktail archetypes
- 1-2 Korean alcohol examples such as soju or makgeolli
- 1-2 sake or liqueur examples if useful for survey coverage

The beta seed target from `docs/plans/009.md` SHOULD cover at least five
reviewed beverages per active MVP category before relying on live map/place
availability data.

Seed import MUST be idempotent. Re-running it must not duplicate catalog items,
flavor profiles, or vectors.

## Minimal Migration Plan

Current foundation migrations already define the minimum MVP tables:

- `beverage_items`
- `flavor_profiles`
- `recommendation_vectors`
- `vector_schema_versions`
- `scoring_configs`
- `qdrant_points`

No new migration is required just to start the beverage catalog foundation if
the current initial migration has not been deployed to shared or production
databases.

If the initial migration has already been applied outside local development,
do not rewrite it. Use additive migrations only.

Optional future additive migration:

```text
0002_add_beverage_catalog_key
- add beverage_items.catalog_key nullable
- backfill from metadata_json.catalog_key or deterministic slug
- add unique index
- set NOT NULL after data is clean
```

Do not add this migration until seed/import or admin tooling needs a database
level natural key. Deterministic UUIDs plus `metadata_json.catalog_key` are
enough for the first seed.

## Qdrant Timing

Allowed now:

- Qdrant config
- Qdrant readiness checks
- `qdrant_points` metadata table

Defer until after beverage seed data exists:

- real collection creation
- real vector upsert
- indexing workers
- Qdrant-backed candidate retrieval

When implemented, Qdrant indexing MUST rebuild from:

```text
beverage_items
  -> flavor_profiles
  -> recommendation_vectors
  -> qdrant_points
```

not from ad hoc seed files or Qdrant payloads.

## Next Implementation Order

1. Add beverage catalog repository methods.
2. Add seed data file with 10-20 curated beverages.
3. Add idempotent seed loader that writes `beverage_items`,
   `flavor_profiles`, and `recommendation_vectors`.
4. Validate every seed vector against `taste_v1`.
5. Add tests for idempotency, vector length, active filtering, and source hash.
6. Add Qdrant collection/indexing wrapper only after PostgreSQL contains
   canonical beverage vectors.

Do not implement ranking logic in this phase.

## Acceptance Criteria

- Active beverages can be loaded from PostgreSQL.
- Each active seed beverage has exactly one current `taste_v1` canonical vector.
- Each beverage vector is reproducible from seed data and version metadata.
- Inactive beverages are excluded from future candidate generation.
- Reason-code hints are stored but not treated as final explanations.
- Qdrant can be fully rebuilt later from PostgreSQL without losing catalog data.
