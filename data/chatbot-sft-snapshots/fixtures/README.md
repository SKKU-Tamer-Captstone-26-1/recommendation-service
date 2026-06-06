# Fixture Index

These fixtures are synthetic examples. They are not production recommendation
logs and are not automatically valid SFT rows.

Required fixture types:

```text
01_beverage_recommendation_explanation
02_venue_recommendation_explanation
03_tradeoff_explanation
04_profile_missing_insufficient_data
05_out_of_scope_refusal
```

Each fixture follows `../schemas/recommendation_snapshot.schema.json`.

Current fixture count:

```text
01_beverage_recommendation_explanation: 5
02_venue_recommendation_explanation: 5
03_tradeoff_explanation: 5
04_profile_missing_insufficient_data: 5
05_out_of_scope_refusal: 5
```

Fixture filenames are stable numeric IDs:

```text
001.json
002.json
003.json
004.json
005.json
```

Before converting a fixture into an SFT candidate, a human reviewer must verify
that the Korean answer uses only `grounded_context` facts and preserves
recommendation-service ranking.
