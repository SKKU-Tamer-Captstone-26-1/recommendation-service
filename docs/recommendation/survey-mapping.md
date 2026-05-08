# Survey Mapping

## Purpose

This document defines how canonical survey responses from `survey-service` are
mapped into derived taste profiles owned by `recommendation-service`.

## Document Contract

### Why This File Exists

- Keeps profile generation reproducible.
- Separates raw survey ownership from derived taste profile ownership.
- Provides a stable mapper version contract for rebuilds.

### What MUST Be Documented Here

- Mapper version.
- Required survey input fields.
- Output profile fields.
- Survey answer to vector mapping rules.
- Budget, category, keyword, and experience mapping.
- Snapshot/hash expectations.

### What MUST NOT Be Documented Here

- Survey database schema.
- Raw survey storage rules inside `survey-service`.
- Recommendation reranking formulas.
- API endpoint details except minimal dependency notes.

### Recommended Sections

1. Purpose
2. Ownership Boundary
3. Current Mapper Version
4. Input Contract
5. Output Contract
6. Mapping Rules
7. Snapshot Strategy
8. Versioning Rules

### Engineering Constraints

- `survey-service` owns raw survey answers.
- `recommendation-service` MUST fetch survey responses through APIs/events.
- `recommendation-service` MUST NOT read the survey database.
- Mapper changes MUST create a new mapper version.
- Generated profiles MUST record survey version, response revision, mapper
  version, and vector schema version.

### Update Rules

- Update when survey input, mapping rules, profile output, or mapper version
  changes.
- Any mapper change must describe rebuild impact.

## Ownership Boundary

`recommendation-service` stores derived profile state only.

Allowed:

- `survey_response_id`
- `survey_version`
- `survey_response_revision`
- source snapshot hash
- optional generation snapshot JSON for audit/debug
- derived taste profile

Forbidden:

- treating raw survey answers as canonical
- editing survey answers
- direct survey database access

## Current Mapper Version: `survey_mapper_v1`

Compatible vector schema:

```text
taste_v1
```

## Input Contract

Minimum fields expected from `survey-service`:

```json
{
  "survey_response_id": "surv_resp_123",
  "external_user_id": "usr_123",
  "survey_version": "survey_v1",
  "response_revision": 1,
  "completed_at": "2026-05-08T12:00:00Z",
  "answers": {
    "experience_level": "beginner",
    "categories": ["whiskey", "cocktail"],
    "category_traits": {
      "whiskey": ["sweet", "smoky"],
      "cocktail": ["sour", "spirit_forward"]
    },
    "global_keywords": ["vanilla_caramel", "nutty", "oak_woody"],
    "budget_range": "30000_100000"
  }
}
```

## Output Contract

Generated profile MUST include:

```json
{
  "external_user_id": "usr_123",
  "survey_response_id": "surv_resp_123",
  "survey_version": "survey_v1",
  "survey_response_revision": 1,
  "mapper_version": "survey_mapper_v1",
  "vector_schema_version": "taste_v1",
  "preferred_categories": ["whiskey", "cocktail"],
  "preferred_keywords": ["vanilla_caramel", "nutty", "oak_woody"],
  "budget_range": "30000_100000",
  "experience_level": "beginner",
  "taste_vector": [0.8, 0.2, 0.2, 0.6, 0.4, 0.7, 0.0, 0.2, 0.0, 0.5, 0.4, 0.0, 0.5, 0.0, 0.0, 0.0]
}
```

## Mapping Rules

Global keywords SHOULD have the strongest weight.

Example keyword mapping:

| Survey Keyword | Primary Dimensions |
|---|---|
| `vanilla_caramel` | `sweet`, `woody` |
| `citrus_berry` | `fruity`, `acidity` |
| `dried_fruit_chocolate` | `dried_fruit`, `roasted`, `sweet` |
| `oak_woody` | `woody`, `spicy`, `tannin` |
| `smoky_peat` | `smoky`, `alcohol_intensity` |
| `nutty` | `nutty`, `body` |
| `floral` | `floral` |
| `spicy` | `spicy`, `woody` |
| `herbal_mint` | `herbal`, `bitterness` |

Experience level affects:

- explanation language
- exploration percentage
- beginner friendliness weight

Experience level MUST NOT directly overwrite taste preferences.

## Snapshot Strategy

For each generated profile, store:

- canonical survey identifiers
- source snapshot hash
- mapper version
- vector schema version
- optional snapshot JSON used for generation

Rebuilds SHOULD fetch fresh canonical data from `survey-service`. Stored
snapshots are for audit and forensic comparison, not source ownership.

## Versioning Rules

Create a new mapper version when:

- survey input shape changes
- answer weights change
- keyword-to-dimension mapping changes
- profile output logic changes
- vector schema compatibility changes

