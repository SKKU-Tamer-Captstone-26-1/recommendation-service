# Assistant RAG and No-Hallucination Policy

## Purpose

This document defines how the ONTHEBLOCK assistant may use RAG and grounded
context.

RAG is allowed only as a context-building and explanation-support mechanism.
RAG MUST NOT be used as the recommendation ranking engine.

This is a pre-implementation policy. It must be implemented with tests before
any production assistant runtime is enabled.

## Core Rule

```text
Recommendation ranking = recommendation-service deterministic output
Assistant answer = LLM rewrite of verified retrieved facts
```

No retrieved evidence means no answer.

## Allowed Grounding Sources

The assistant MAY answer from these verified facts:

| Source | Owner | Allowed Use |
|---|---|---|
| Taste profile summary | `recommendation-service` | Explain user preferences |
| Beverage recommendation candidates | `recommendation-service` | Recommend alcohol |
| Venue recommendation candidates | `recommendation-service` | Recommend places to buy or drink |
| Score breakdowns | `recommendation-service` | Explain ranking factors |
| Reason codes | `recommendation-service` | Generate deterministic explanations |
| Map/place read-model snapshots | `recommendation-service` | Explain place, price, inventory, distance facts |
| Freshness and confidence metadata | `recommendation-service` | Warn about stale or uncertain facts |
| Human-reviewed empirical review summaries | Approved content curation pipeline | Explain common user experience patterns only |
| App policy documents | Repository docs or policy service | Refusal and scope behavior |

## Disallowed Sources

The assistant MUST NOT answer recommendation questions from:

- model memory
- general web search
- unverified chat history
- raw survey answers
- direct survey-service database access
- direct map-service database access
- Qdrant-only facts
- Kakao Local API data stored outside approved policy

The assistant MUST NOT treat RAG chunks as source of truth for:

- current inventory
- current price
- live business status
- route time
- opening hours
- recommendation score
- place existence

## Personal Opinion / Empirical Review Policy

Personal blogs, community posts, and tasting reviews MAY be used only after
human review and source-policy approval.

Allowed use:

- summarize repeated experience patterns, such as "many reviewers describe this
  as sweet, smoky, or beginner-friendly"
- enrich recommendation explanations after `recommendation-service` has already
  produced deterministic candidates and ranking
- preserve source metadata for internal audit
- paraphrase; do not copy long source text into prompts or answers

Forbidden use:

- use personal opinions as recommendation score, rank, inventory, price,
  location, opening-hour, or availability truth
- use a single person's opinion as if it is objective product fact
- scrape or store personal blog content without licensing, permission, or an
  approved content policy
- expose private author information, comments, or user identifiers

If an answer uses empirical review summaries, the user-facing response MUST show
this Korean warning:

```text
이 추천은 사람들의 경험과 개인적 의견을 종합한 경험적 추천입니다. 개인차가 있을 수 있으므로 참고용으로만 확인해 주세요.
```

If the assistant cannot preserve this warning with the answer, it MUST avoid
using personal-opinion context.

## Grounded Context Requirements

Each grounded context item MUST preserve internal traceability metadata.

Recommended metadata:

```json
{
  "source_type": "recommendation_result",
  "source_service": "recommendation-service",
  "request_id": "rec_req_123",
  "result_id": "rec_result_456",
  "profile_revision": 4,
  "scoring_config_version": "venue_score_v1",
  "place_revision": "place_rev_12",
  "inventory_revision": "inv_rev_8",
  "price_revision": "price_rev_3",
  "confidence": 0.86,
  "freshness_status": "fresh"
}
```

Internal IDs SHOULD be retained for audit and debugging. The user-facing answer
SHOULD hide raw IDs unless the product contract requires them.

## No-Answer Policy

The assistant MUST refuse or return insufficient data when:

- the user asks an unrelated general question
- the request is outside ONTHEBLOCK alcohol, preference, or venue scope
- the user has no usable recommendation profile
- no recommendation-service facts are returned
- required location is missing for nearby venue intent
- inventory, price, or distance facts are stale beyond configured thresholds
- confidence is below configured thresholds
- the LLM draft contains claims not present in grounded context

Default refusal text:

```text
I can only help with ONTHEBLOCK alcohol, preference, and nearby venue recommendations.
```

Default insufficient-data text:

```text
I cannot find a reliable recommendation from the current ONTHEBLOCK data.
```

Low-confidence place text:

```text
I found a likely match, but the inventory information is not fully confirmed.
```

## Out-of-Scope Detection

Out-of-scope requests include:

- general trivia
- medical, legal, financial, or political advice
- unrelated travel planning
- generic restaurant recommendations without alcohol or ONTHEBLOCK venue context
- requests to invent products, places, prices, or availability
- attempts to override system or source-grounding rules

The assistant MAY ask a clarifying question only when the user request appears
related to ONTHEBLOCK but required facts are missing.

## Low-Confidence Handling

Confidence thresholds MUST be configuration-driven.

The assistant SHOULD distinguish:

| State | Behavior |
|---|---|
| `fresh_high_confidence` | Answer normally |
| `fresh_low_confidence` | Answer with uncertainty if product allows |
| `stale_high_confidence` | Warn about staleness |
| `stale_low_confidence` | Return insufficient data |
| `missing_fact` | Return insufficient data or ask follow-up |

The assistant MUST NOT silently upgrade low-confidence facts into confident
claims.

## Response Verifier

Before returning an answer, the assistant MUST verify:

- every beverage name appears in grounded context
- every place name appears in grounded context
- every price appears in grounded context
- every inventory claim appears in grounded context
- every distance or travel-time claim appears in grounded context
- every explanation claim maps to reason codes, scores, or profile summary
- refusal is used when required facts are missing

If verification fails, the assistant MUST return a refusal or insufficient-data
response instead of the generated answer.

## Prompt Injection Policy

The assistant MUST treat user messages as untrusted input.

User messages MUST NOT be allowed to:

- change system instructions
- disable source grounding
- request hidden metadata
- force unsupported tool calls
- override refusal policy
- cause direct database access

## Warm-Up Learning Strategy

Warm-up learning is a future research-inspired idea for reducing assistant
overconfidence.

For MVP, do not implement training, fine-tuning, or online learning.

MVP guardrails MUST come first:

- negative examples
- out-of-scope examples
- no-answer evaluation set
- retrieval confidence threshold
- response verifier
- refusal templates

Future warm-up learning work MUST have a separate design before implementation.
That design must cover data ownership, privacy, evaluation, rollback, and
failure handling.

## Update Rules

- Update this document when grounding sources, refusal rules, confidence states,
  or verifier requirements change.
- Do not document provider-specific credentials here.
- Keep response fields in `response-schema.md`.
