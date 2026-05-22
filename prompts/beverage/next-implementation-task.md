# Task: Validate Expanded Beverage Candidate Files and Implement Staging Import

You are Codex working in `/Users/jeonghun/recommendation-service`.

Use the custom agent or implementation workflow appropriate to the task. Start
by reading:

```text
AGENTS.md
.agent/HARNESS.md
docs/beverage/beverage-data-collection-report.md
docs/beverage/beverage-source-policy.md
docs/beverage/beverage-taxonomy.md
docs/beverage/beverage-staging-db-mapping.md
prompts/beverage/create-beverage-staging-schema.md
```

## Goal

Make the expanded beverage candidate batch importable into local/dev staging
only.

Current input files:

```text
data/beverage/run_manifest.json
data/beverage/source_registry.csv
data/beverage/catalog_candidates.jsonl
data/beverage/flavor_profile_candidates.jsonl
data/beverage/knowledge_candidates.jsonl
data/beverage/price_observation_candidates.jsonl
```

Current candidate counts from `bev_collect_2026_05_22_mvp_expansion_002`:

| Lane | Count |
|---|---:|
| catalog candidates | 120 |
| flavor profile candidates | 120 |
| knowledge candidates | 120 |
| price observations | 11 |
| source registry rows | 131 |

## Required Sequence

1. Implement the staging schema described in
   `prompts/beverage/create-beverage-staging-schema.md`.
2. Implement a dry-run validator/importer.
3. Run dry-run against the current `data/beverage/` batch.
4. If dry-run passes and the environment is local/dev, apply to staging only.
5. Report inserted row counts and validation warnings.

## Hard Rules

Do not:

```text
- write canonical beverage tables
- write production DB
- write map/admin/auth/survey DBs
- mark records approved
- create Qdrant points
- use RAG chunks for ranking
```

## Validation Requirements

The importer must verify:

- JSONL files parse line by line.
- CSV source registry parses with stable headers.
- Every candidate status is not `approved`.
- Candidate IDs are unique.
- Flavor vectors contain only values from 0.0 to 1.0.
- Flavor, knowledge, and price records reference existing catalog candidates.
- Price observations with retailer sources are marked as non-live observations.
- Source URLs are preserved.

## Output

Final response should include:

```text
Summary
Changed files
Verification
DB/staging actions
Risks / Follow-ups
```
