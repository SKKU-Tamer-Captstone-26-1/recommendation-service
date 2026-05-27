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
- Survey snapshots stored by recommendation-service are generation evidence, not
  raw survey ownership.

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
- optional redacted generation snapshot JSON for audit/debug
- derived taste profile

Forbidden:

- treating raw survey answers as canonical
- editing survey answers
- direct survey database access
- using stored snapshots as the rebuild source when survey-service is available

## Current Mapper Version: `survey_mapper_v1_1`

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

The deployed `ontheblock.survey.v1.SurveyResult` contract observed on
2026-05-27 uses category-based answer keys:

```json
{
  "survey_id": "surv_resp_123",
  "user_id": "usr_123",
  "level": "expert",
  "categories": ["whiskey", "wine", "cognac", "beer", "cocktail"],
  "whiskey": ["bourbon_character", "sherry_character", "peat_character"],
  "wine": ["full_red", "sparkling"],
  "cocktail": ["tropical_tiki", "tart_balanced"],
  "beer": ["lager_pilsner", "pale_ale_ipa"],
  "flavor_keywords": ["vanilla_caramel", "citrus_berry", "dried_choco"],
  "budget": "over_200k",
  "submitted_at": "2026-05-26T12:06:04Z"
}
```

The deployed adapter normalizes this shape before profile generation:

| SurveyResult field/value | Mapper input |
|---|---|
| `survey_id` | `survey_response_id` |
| `user_id` | `external_user_id` |
| `level` | `answers.experience_level` |
| `categories` | `answers.categories` |
| `cognac` category | `brandy_cognac` category |
| `whiskey`, `wine`, `cocktail`, `beer` arrays | `answers.category_traits` |
| empty category arrays | omitted from `answers.category_traits` |
| `flavor_keywords` | `answers.global_keywords` |
| `budget` | normalized `answers.budget_range` |
| `submitted_at` | `completed_at` |

Budget normalization:

| Survey budget | Mapper budget |
|---|---|
| `under_30k` | `under_30000` |
| `30k_100k` | `30000_100000` |
| `100k_200k` | `100000_200000` |
| `over_200k` | `over_200000` |

`cognac` has no separate sub-preference field in the deployed survey contract.
It is still retained as a category signal by mapping it to the internal beverage
catalog category `brandy_cognac`.

## Output Contract

Generated profile MUST include:

```json
{
  "external_user_id": "usr_123",
  "survey_response_id": "surv_resp_123",
  "survey_version": "survey_v1",
  "survey_response_revision": 1,
  "mapper_version": "survey_mapper_v1_1",
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
| `dried_choco` | `dried_fruit`, `roasted`, `sweet` |
| `oak_woody` | `woody`, `spicy`, `tannin` |
| `smoky_peat` | `smoky`, `alcohol_intensity` |
| `smoky_peated` | `smoky`, `alcohol_intensity` |
| `nutty`, `almond_nutty` | `nutty`, `body` |
| `floral` | `floral` |
| `spicy` | `spicy`, `woody` |
| `herbal_mint`, `herb_mint` | `herbal`, `bitterness` |

Category-style tokens from the deployed contract are also treated as mapper
evidence:

| Category | Survey Tokens |
|---|---|
| `whiskey` | `bourbon_character`, `sherry_character`, `peat_character`, `floral_citrus`, `american_whiskey` |
| `wine` | `full_red`, `light_red_rose`, `white`, `sparkling`, `fortified` |
| `cocktail` | `tropical_tiki`, `tart_balanced`, `refreshing_long`, `dessert_cream`, `bold_spirit_fwd` |
| `beer` | `lager_pilsner`, `weizen_white`, `pale_ale_ipa`, `stout_porter`, `sour_wild` |

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
- optional redacted snapshot JSON used for generation

Rebuilds SHOULD fetch fresh canonical data from `survey-service`. Stored
snapshots are for audit and forensic comparison, not source ownership.

If a snapshot is stored, it SHOULD contain only fields required to reproduce the
mapper input and debug the generated profile. It MUST NOT become the canonical
survey record.

## Versioning Rules

Create a new mapper version when:

- survey input shape changes
- answer weights change
- keyword-to-dimension mapping changes
- profile output logic changes
- vector schema compatibility changes
