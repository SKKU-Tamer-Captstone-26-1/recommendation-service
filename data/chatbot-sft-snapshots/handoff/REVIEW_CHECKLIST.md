# Chatbot SFT Snapshot Review Checklist

## Required Checks

Approve a snapshot or SFT candidate only if all checks pass.

| Check | Pass Rule |
|---|---|
| Source boundary | Facts come from recommendation-service outputs or approved service APIs only. |
| PII and secrets | No raw JWTs, access tokens, passwords, emails, phone numbers, or raw user IDs. |
| Raw survey boundary | No raw survey-service answer rows. Only derived profile summaries. |
| Map/place boundary | No direct map-service DB rows. Only recommendation snapshots/read-model facts. |
| Ranking preservation | Assistant answer preserves recommendation-service ranking. |
| Beverage grounding | Every beverage name appears in grounded context. |
| Venue grounding | Every venue/place name appears in grounded context. |
| Price grounding | Every price appears in grounded context. |
| Distance grounding | Every distance appears in grounded context. |
| Atmosphere grounding | Atmosphere terms appear in grounded context. |
| Availability grounding | Inventory or stock claims match context and freshness. |
| Refusal behavior | Missing profile, insufficient data, and out-of-scope requests refuse correctly. |
| User-facing IDs | Raw internal IDs are not exposed unless explicitly required. |

## Automatic Rejection Cases

Reject if the answer:

- invents a beverage, venue, price, stock state, distance, flavor, scent, or user
  preference
- answers unrelated general questions
- treats the LLM as the recommendation ranker
- changes first/second/third recommendation order
- uses raw survey answers directly
- claims live inventory or live opening hours without verified freshness
- includes secrets or personal information

## Reviewer Notes

When rejecting a candidate, record:

```text
snapshot_id
failure reason
unsupported phrase
missing source field
recommended fix
```

When approving a candidate, record:

```text
snapshot_id
reviewer
date
risk flags, if any
```
