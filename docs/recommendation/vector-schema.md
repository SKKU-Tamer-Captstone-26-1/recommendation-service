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

## Category Strategy

`taste_v1` is shared across categories. Category-specific behavior belongs in:

- scoring config weights
- mapper rules
- catalog curation rules

Do not create category-specific meanings for the same dimension.

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

