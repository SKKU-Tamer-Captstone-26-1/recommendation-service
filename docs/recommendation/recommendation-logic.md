# Recommendation Logic

## Purpose

This document defines the explainable V1 recommendation pipeline. It is the
source of truth for candidate generation, filtering, reranking, score breakdowns,
and explanation behavior.

## Document Contract

### Why This File Exists

- Keeps recommendation behavior deterministic and reviewable.
- Gives backend and AI engineers one place to evolve ranking logic.
- Prevents hidden scoring rules from being embedded only in code.

### What MUST Be Documented Here

- Pipeline stages.
- Hard filters and soft ranking features.
- Score breakdown fields.
- Explanation reason-code strategy.
- Category-specific ranking behavior.
- Recommendation logging requirements.

### What MUST NOT Be Documented Here

- Vector dimension definitions. Use `vector-schema.md`.
- Survey answer mapping. Use `survey-mapping.md`.
- API response schemas. Use `../api/recommendation-api.md`.
- Table definitions. Use `../database/erd.md`.

### Recommended Sections

1. Purpose
2. Pipeline Overview
3. Candidate Generation
4. Hard Filters
5. Vector Retrieval
6. Reranking
7. Diversity and Exploration
8. Explainability
9. Logging
10. Update Rules

### Engineering Constraints

- Recommendations MUST be reproducible from profile revision, vector schema,
  mapper version, scoring config, catalog state, and request filters.
- V1 explanations MUST be deterministic templates and reason codes.
- Random ranking behavior MUST NOT be introduced without a stored seed and config.
- Scoring config changes MUST be versioned.

### Update Rules

- Update when filters, weights, score fields, explanation rules, or ranking stages
  change.
- Any scoring change must identify whether historical results remain comparable.

## Pipeline Overview

```text
1. Resolve authenticated external_user_id.
2. Load active taste_profile_revision.
3. Apply request-level constraints.
4. Retrieve broad candidates from Qdrant.
5. Hydrate candidates from PostgreSQL.
6. Apply hard filters.
7. Rerank with versioned scoring config.
8. Apply diversity/exploration rules.
9. Generate deterministic explanations.
10. Persist recommendation request, results, explanations, and interactions.
```

## Candidate Generation

Candidate sources:

| Target Type | Source |
|---|---|
| Beverage | `beverage_items` + beverage vector collection |
| Venue | `venue_snapshots`, `venue_inventory_snapshots`, `venue_price_snapshots`, venue vector collection |
| Menu item | `venue_menu_snapshots` + menu item vector collection |

Qdrant SHOULD retrieve more candidates than the API limit so reranking can apply
metadata and diversity rules.

Venue and menu-item sources are read-model snapshots from
map-service/place-service. They are not canonical place/menu/inventory/price
tables.

## Hard Filters

Hard filters remove candidates before final scoring:

- inactive catalog item
- unsupported category
- unavailable market flag
- outside requested venue radius
- hidden, closed, merged, or unpublished venue snapshot
- expired inventory snapshot when no fallback is allowed
- expired price snapshot when strict budget comparison is requested
- incompatible price range when caller requests strict budget filtering
- blocked or administratively hidden item

Hard filters MUST be visible in debug logs for internal requests.

## Reranking

Final score SHOULD be composed of explicit score components:

```text
final_score =
  taste_similarity_weighted
  + budget_fit
  + category_fit
  + experience_fit
  + popularity_or_quality
  + distance_fit
  + availability_confidence
  + price_confidence
  + freshness_adjustment
  + diversity_adjustment
```

Every response result MUST store:

- raw vector similarity
- final score
- score breakdown JSON
- scoring config version
- profile revision ID
- target type and target ID
- source snapshot revisions for venue results

## Category-Specific Behavior

Category-specific behavior SHOULD be implemented with scoring config weights,
not by changing vector semantics in place.

Examples:

| Category | Higher Weight Dimensions |
|---|---|
| whiskey | `sweet`, `woody`, `smoky`, `body`, `alcohol_intensity` |
| wine | `fruity`, `acidity`, `tannin`, `body`, `floral` |
| beer | `bitterness`, `carbonation`, `body`, `roasted`, `acidity` |
| cocktail | `sweet`, `acidity`, `herbal`, `carbonation`, `alcohol_intensity` |

## Diversity and Exploration

Exploration MUST be bounded and explainable.

Recommended default:

| Experience Level | Core Matches | Adjacent Exploration |
|---|---:|---:|
| beginner | 90% | 10% |
| enthusiast | 80% | 20% |
| expert | 70% | 30% |

Exploration candidates MUST still pass hard filters and minimum similarity.

## Explainability

Each recommendation result MUST include:

- reason codes
- matched vector dimensions
- category/style explanation
- budget or distance explanation when relevant
- template version

Example reason codes:

```text
MATCHES_VANILLA_CARAMEL
MATCHES_SMOKY_PROFILE
BEGINNER_FRIENDLY
WITHIN_BUDGET
NEARBY_VENUE
ADJACENT_DISCOVERY
```

Explanation text MUST be generated from stored reason codes and score
contributions. V1 MUST NOT depend on unbounded LLM-generated explanations.

LLM or assistant-generated prose MAY rewrite deterministic explanations only when
the grounded context includes the original reason codes and score metadata. It
MUST NOT change ranking or invent reasons.

## Logging

Persist:

- recommendation request
- ranked results
- score breakdowns
- explanation payloads
- map/place snapshot revisions for venue results
- user interactions such as click, save, dismiss, and detail view

Recommendation logs are product analytics and debugging data. They are not raw
survey truth.
