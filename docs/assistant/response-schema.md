# Assistant Response Schema

## Purpose

This document defines the draft API and response shape for the ONTHEBLOCK
assistant.

This is not a finalized protobuf contract. Do not generate code from this
document until the project accepts an assistant proto workflow.

This schema is a pre-implementation draft. It defines expected behavior and
review targets, not generated API code.

## API Principles

- gRPC is the default MSA service-to-service contract.
- User identity MUST come from authenticated JWT/gateway context.
- The request body MUST NOT accept `user_id`.
- Responses MUST distinguish answer, refusal, missing facts, and source metadata.
- Recommendation cards MUST be backed by recommendation-service facts.
- Internal traceability metadata MUST be preserved.

## Draft Service Shape

```proto
service AssistantService {
  rpc AskAssistant(AskAssistantRequest) returns (AskAssistantResponse);
}
```

## AskAssistantRequest

| Field | Required | Meaning |
|---|---|---|
| `message` | yes | User message |
| `lat` | no | Latitude for nearby venue requests |
| `lng` | no | Longitude for nearby venue requests |
| `radius_m` | no | Search radius in meters |
| `budget_hint` | no | Optional user-provided budget hint |
| `conversation_id` | no | Conversation correlation ID |

Identity fields are intentionally absent.

Authenticated identity is resolved as:

```text
gateway/auth context -> JWT sub -> external_user_id
```

## AskAssistantResponse

| Field | Meaning |
|---|---|
| `answer` | User-facing natural-language answer |
| `intent` | Detected assistant intent |
| `confidence` | Assistant response confidence after grounding and verification |
| `refused` | Whether the assistant refused or could not answer |
| `refusal_reason` | Typed refusal reason |
| `cards` | Structured recommendation cards |
| `used_sources` | Internal source metadata for traceability |
| `missing_facts` | Facts required but not available |
| `follow_up_questions` | Optional clarifying questions |

## Intent Values

```text
recommend_beverage
find_nearby_venue
compare_purchase_options
explain_preference
explain_recommendation
profile_status
out_of_scope
insufficient_data
```

## Refusal Reasons

```text
out_of_scope
profile_missing
profile_pending
profile_stale_unusable
profile_failed
location_required
no_recommendation_facts
low_confidence
stale_data
missing_required_fact
response_verification_failed
```

## Card Types

Supported MVP card types:

```text
beverage
venue
purchase_option
comparison
```

## Beverage Card

```json
{
  "type": "beverage",
  "title": "Example Bourbon",
  "subtitle": "Smoky, full-bodied whiskey",
  "rank": 1,
  "score": 0.91,
  "reason_codes": ["MATCHES_SMOKY_PROFILE", "FULL_BODIED"],
  "explanation": "Matches your smoky and full-bodied preference."
}
```

## Venue Card

```json
{
  "type": "venue",
  "title": "Example Bottle Shop",
  "subtitle": "Liquor store",
  "distance_m": 720,
  "availability_status": "likely_available",
  "inventory_confidence": 0.82,
  "price_krw": 42000,
  "price_confidence": 0.78,
  "reason_codes": ["NEARBY_VENUE", "WITHIN_BUDGET"]
}
```

## Purchase Option Card

```json
{
  "type": "purchase_option",
  "option_type": "balanced_best",
  "title": "Best balanced option",
  "place_name": "Example Bottle Shop",
  "beverage_name": "Example Bourbon",
  "distance_m": 720,
  "price_krw": 42000,
  "availability_status": "likely_available",
  "tradeoff_summary": "Strong taste match with reliable inventory and reasonable distance."
}
```

## Comparison Card

```json
{
  "type": "comparison",
  "title": "Purchase options",
  "options": [
    {
      "option_type": "nearest_reasonable",
      "place_name": "Nearby Market",
      "distance_m": 350,
      "price_krw": 46000
    },
    {
      "option_type": "best_price",
      "place_name": "Value Liquor",
      "distance_m": 1300,
      "price_krw": 39000
    }
  ]
}
```

## Used Sources

`used_sources` is primarily internal metadata.

```json
{
  "source_type": "venue_recommendation",
  "source_service": "recommendation-service",
  "request_id": "rec_req_123",
  "result_id": "rec_result_456",
  "profile_revision": 4,
  "scoring_config_version": "venue_score_v1",
  "place_id": "place_123",
  "place_revision": "place_rev_12",
  "inventory_revision": "inv_rev_8",
  "price_revision": "price_rev_3",
  "confidence": 0.84
}
```

User-facing clients SHOULD NOT display raw internal IDs by default.

## Missing Facts

Examples:

```text
profile
lat_lng
beverage_recommendations
venue_recommendations
price
inventory_status
distance
freshness_metadata
```

## Example: Sufficient Data

```json
{
  "answer": "Based on your preference for smoky and full-bodied drinks, these three options match you best.",
  "intent": "recommend_beverage",
  "confidence": 0.88,
  "refused": false,
  "refusal_reason": "",
  "cards": [],
  "used_sources": [],
  "missing_facts": [],
  "follow_up_questions": []
}
```

## Example: Low Inventory Confidence

```json
{
  "answer": "I found a likely match, but the inventory information is not fully confirmed.",
  "intent": "find_nearby_venue",
  "confidence": 0.52,
  "refused": false,
  "refusal_reason": "",
  "cards": [],
  "used_sources": [],
  "missing_facts": ["confirmed_inventory"],
  "follow_up_questions": []
}
```

## Example: No Data

```json
{
  "answer": "I cannot find a reliable recommendation from the current ONTHEBLOCK data.",
  "intent": "insufficient_data",
  "confidence": 0.0,
  "refused": true,
  "refusal_reason": "no_recommendation_facts",
  "cards": [],
  "used_sources": [],
  "missing_facts": ["beverage_recommendations"],
  "follow_up_questions": []
}
```

## Example: Out of Scope

```json
{
  "answer": "I can only help with ONTHEBLOCK alcohol, preference, and nearby venue recommendations.",
  "intent": "out_of_scope",
  "confidence": 1.0,
  "refused": true,
  "refusal_reason": "out_of_scope",
  "cards": [],
  "used_sources": [],
  "missing_facts": [],
  "follow_up_questions": []
}
```

## Update Rules

- Update this document before creating or changing assistant protobufs.
- Keep final generated protobuf files out of this document.
- Keep prompt behavior in `prompt-contract.md`.
- Keep grounding policy in `rag-policy.md`.
