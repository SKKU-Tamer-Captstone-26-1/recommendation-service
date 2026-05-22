# Vector Schema

## Purpose

This document defines the versioned taste vector schema used by
`recommendation-service`. It is the source of truth for vector dimensions,
dimension order, value semantics, and schema evolution.

## Document Contract

### Why This File Exists

- Keeps user, beverage, venue, and menu-item vectors comparable.
- Makes profile regeneration reproducible.
- Prevents silent changes to vector meaning.
- Provides a clean path to future ML embeddings.

### What MUST Be Documented Here

- Vector schema version.
- Dimension order.
- Dimension meanings.
- Value range and unknown semantics.
- Compatibility rules.
- Category-specific weighting relationship.
- Migration requirements for new vector versions.

### What MUST NOT Be Documented Here

- Survey question mapping details. Use `survey-mapping.md`.
- Reranking formulas. Use `recommendation-logic.md`.
- Qdrant table metadata. Use `../database/erd.md`.

### Recommended Sections

1. Purpose
2. Current Schema
3. Dimension Table
4. Value Semantics
5. Confidence Semantics
6. Compatibility Rules
7. Category Strategy
8. Version Migration Rules

### Engineering Constraints

- Dimension order MUST NOT change within the same schema version.
- Dimension meaning MUST NOT change within the same schema version.
- New dimensions require a new vector schema version.
- Unknown MUST be distinguishable from true zero through confidence metadata.
- PostgreSQL stores canonical vectors; Qdrant stores derived indexed vectors.

### Update Rules

- Update only when vector semantics change.
- Any change to current dimensions requires creating a new schema section.
- Every new schema version must include rebuild instructions.

## Current Schema: `taste_v1`

Implementation status:

```text
pre-implementation frozen candidate
```

Do not change `taste_v1` during initial implementation unless the change creates
a new documented schema version before migrations are written.

Distance metric:

```text
cosine
```

Value range:

```text
0.0 to 1.0
```

Dimension order:

| Index | Dimension | Meaning |
|---:|---|---|
| 0 | `sweet` | Sweetness, dessert-like notes, sugar impression |
| 1 | `fruity` | Fresh fruit, citrus, berry, tropical fruit |
| 2 | `dried_fruit` | Raisin, fig, date, jam, dark fruit |
| 3 | `woody` | Oak, barrel, cedar, wood spice |
| 4 | `smoky` | Smoke, peat, char, roasted smoke |
| 5 | `nutty` | Almond, hazelnut, walnut, grain nuttiness |
| 6 | `floral` | Flowers, perfume, delicate aromatics |
| 7 | `spicy` | Baking spice, pepper, warm spice |
| 8 | `herbal` | Mint, herbs, botanical notes |
| 9 | `body` | Weight, richness, mouthfeel |
| 10 | `acidity` | Tartness, sourness, brightness |
| 11 | `carbonation` | Sparkle, fizz, effervescence |
| 12 | `alcohol_intensity` | Heat, spirit-forward strength |
| 13 | `bitterness` | Hop bitterness, bitter finish, bitter botanicals |
| 14 | `tannin` | Drying grip, wine structure, oak astringency |
| 15 | `roasted` | Coffee, cocoa, toast, roasted malt |

## Value Semantics

Values represent affinity or profile strength, not objective chemical
measurement.

```json
{
  "sweet": 0.8,
  "smoky": 0.1,
  "body": 0.6
}
```

Rules:

- `1.0` means strong preference or strong product expression.
- `0.0` means explicitly absent only when confidence is high.
- Unknown data MUST be represented through confidence metadata.

## Confidence Semantics

Each vector owner SHOULD have confidence metadata:

```json
{
  "sweet": 0.9,
  "smoky": 0.7,
  "tannin": 0.2
}
```

Low confidence means the value may be missing or weakly inferred. It does not
mean the user dislikes the trait.

## Beverage Vector Contract

Beverage vectors are canonical recommendation-owned vectors stored in
PostgreSQL before any Qdrant indexing.

Required storage:

```text
beverage_items
  -> flavor_profiles(owner_type = beverage_item)
  -> recommendation_vectors(owner_type = beverage_item, vector_schema = taste_v1)
  -> qdrant_points only after indexing is implemented
```

Rules:

- Each active MVP beverage SHOULD have one current `taste_v1` vector.
- `recommendation_vectors.vector` MUST follow the exact `taste_v1` dimension
  order.
- `recommendation_vectors.vector_json` MUST preserve named dimensions for
  debugging and explanation.
- `recommendation_vectors.confidence_json` MUST preserve confidence by
  dimension.
- `source_hash` MUST change when curated beverage flavor metadata changes.
- Inactive beverage items MUST be excluded from candidate generation even if
  their vectors remain stored for audit or future reactivation.
- Qdrant beverage points MUST be rebuilt from PostgreSQL vectors and MUST NOT be
  treated as canonical beverage vector storage.

Reason-code hints may be stored with beverage curation metadata, but final
reason-code emission belongs to versioned scoring rules.

Beverage catalog details are documented in `beverage-catalog.md`.

## Category Strategy

`taste_v1` is shared across categories. Category-specific behavior belongs in:

- scoring config weights
- mapper rules
- catalog curation rules

Do not create category-specific meanings for the same dimension.

## ML Embedding Strategy

Future ML embeddings MUST be stored as separate vector families or schema
versions. They MUST NOT silently replace `taste_v1` semantics.

Example future vector families:

```text
taste_v1              -- explainable taste dimensions
beverage_text_embed_v1 -- model embedding for beverage text search
venue_text_embed_v1    -- model embedding for venue text search
```

Explainable recommendation scoring MUST keep reason-code traceability even when
future ML embeddings are added.

## Version Migration Rules

Create a new vector schema version when:

- adding a dimension
- removing a dimension
- changing dimension order
- changing dimension meaning
- changing distance metric

Migration checklist:

```text
1. Add new vector schema documentation.
2. Add mapper version compatible with the new schema.
3. Add scoring config compatible with the new schema.
4. Regenerate profile vectors in PostgreSQL.
5. Rebuild Qdrant collections.
6. Verify counts, hashes, and sample recommendations.
```
