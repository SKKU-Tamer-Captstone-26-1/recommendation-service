# Chatbot SFT Recommendation Snapshot Package

## Purpose

This folder prepares safe recommendation-service output snapshots for future
human-authored Korean chatbot SFT examples.

This package is not model training. It does not implement assistant runtime,
RAG storage, fine-tuning, or model serving.

The chatbot is a grounded Korean response generator. It may rewrite facts into a
natural answer, but it must not invent alcohol, venues, prices, stock status,
distances, flavors, scents, user preferences, or ranking.

## Package Boundary

Allowed sources:

```text
recommendation-service profile status
recommendation-service beverage recommendation results
recommendation-service venue recommendation results
recommendation-service reason codes and explanations
recommendation-service map/place read-model snapshot metadata
approved service API outputs copied into recommendation snapshots
```

Disallowed sources:

```text
raw JWT or access tokens
passwords or service secrets
raw survey-service database rows
raw map-service database rows
raw auth-service database rows
unverified chat history
web search facts
Qdrant-only facts
Kakao data outside approved source policy
```

## Folder Layout

```text
data/chatbot-sft-snapshots/
- README.md
- manifest.example.json
- schemas/
  - recommendation_snapshot.schema.json
  - sft_candidate.schema.json
- fixtures/
  - 01_beverage_recommendation_explanation/
    - 001.json ... 005.json
  - 02_venue_recommendation_explanation/
    - 001.json ... 005.json
  - 03_tradeoff_explanation/
    - 001.json ... 005.json
  - 04_profile_missing_insufficient_data/
    - 001.json ... 005.json
  - 05_out_of_scope_refusal/
    - 001.json ... 005.json
- handoff/
  - HUMAN_WORKFLOW.md
  - REVIEW_CHECKLIST.md
```

## Five Required Snapshot Types

| Type | Purpose |
|---|---|
| `beverage_recommendation_explanation` | Explain beverage recommendations from ranked recommendation-service results. |
| `venue_recommendation_explanation` | Explain venue, bar, or pub recommendations from ranked recommendation-service results. |
| `tradeoff_explanation` | Explain price, distance, and atmosphere trade-offs without changing ranking. |
| `profile_missing_insufficient_data` | Return safe fallback when profile or required recommendation facts are missing. |
| `out_of_scope_refusal` | Refuse unrelated questions without adding external facts. |

Each type currently has five synthetic draft fixtures. Every fixture must remain
`human_review.status = "draft"` until a human reviewer approves it outside this
package.

## Validation

Run the lightweight validation script after adding or editing fixtures:

```bash
python3 scripts/validate_chatbot_sft_snapshots.py
```

The validator checks JSON parseability, required fields, stable snapshot IDs,
fixture counts, draft review state, no training flags, recommendation ranks,
out-of-scope refusal behavior, and insufficient-data missing facts.

## Human Use

Humans may use these snapshots to write Korean SFT examples later.

The recommended conversion is:

```text
recommendation snapshot
  -> human review
  -> Korean assistant answer draft
  -> grounding review
  -> SFT candidate JSONL
  -> eval set split
```

The snapshot itself is not automatically training data. A reviewer must confirm:

- every factual claim appears in `grounded_context`
- recommendation order is preserved
- refusal is used when facts are missing or scope is invalid
- no raw IDs are exposed in user-facing text unless explicitly allowed
- no secrets, raw survey rows, or cross-service DB payloads are present

## Relationship To Source Documents

This package follows:

- `docs/assistant/assistant-architecture.md`
- `docs/assistant/rag-policy.md`
- `docs/assistant/prompt-contract.md`
- `docs/assistant/response-schema.md`
- `docs/assistant/evaluation-policy.md`
- `docs/recommendation/recommendation-logic.md`
- `docs/recommendation/map-read-model.md`

If those documents change, update this package before creating new SFT
candidates.
