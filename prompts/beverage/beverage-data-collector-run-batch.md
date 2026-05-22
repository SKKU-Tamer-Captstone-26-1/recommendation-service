# Task: Run Beverage Data Collection Batch

You are the `beverage-data-collector` custom Codex agent.

Run one beverage data collection batch.

Inputs to set before running:

```text
CATEGORY=<category>
TARGET_COUNT=<number>
MARKET_FOCUS=Korea + global recognizable
OUTPUT_DIR=data/beverage
STAGING_MODE=dry-run | apply-staging
```

Hard rules:

```text
- Candidate files first.
- Staging DB only if explicitly requested and safe.
- No canonical writes.
- No production DB.
- No long copied source text.
- No fabricated prices or tasting notes.
```

For the selected category:

1. Find target beverages.
2. Prefer official and high-confidence sources.
3. Use blogs/community/personal reviews only as supporting evidence.
4. Write catalog candidates.
5. Write flavor profile candidates.
6. Write RAG knowledge candidates.
7. Write rough price observations if available.
8. Validate JSONL/CSV.
9. Dry-run staging import if available.
10. Report counts and gaps.

Final response in Korean:

```text
Summary
Category / target count
Sources reviewed
Candidate counts
Price observations
Staging actions
Verification
Risks / Follow-ups
Next batch recommendation
```
