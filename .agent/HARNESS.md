# Codex Harness

This document defines the required working loop for Codex.

The purpose of this harness is to prevent Codex from making fast but incorrect
changes across service boundaries.

Codex must follow this harness for all non-trivial tasks.

## H0. Task Intake

Restate the task in one paragraph.

Identify the task type:

```text
documentation
schema
migration
API
admin workflow
map/place ingestion
recommendation logic
RAG/knowledge
assistant
integration
test
bugfix
refactor
```

Identify the target service:

```text
auth-service
map-service
place-service
recommendation-service
survey-service
chatbot-service
admin-page
shared
unknown
```

If target service is unknown, stop and ask.

## H1. Context Load

Read the required documents from `AGENTS.md`.

For each task, Codex must identify:

- relevant existing files
- relevant ownership rules
- relevant DB tables
- relevant APIs
- relevant migrations
- relevant tests
- relevant docs

Codex must not start implementation before this step.

## H2. Boundary Gate

Before planning, answer these questions:

```text
1. Who owns the canonical data being changed?
2. Is this service allowed to write this data?
3. Is this service allowed to read this data directly?
4. Should this be an API call, event, snapshot, or direct DB operation?
5. Is the Admin Page acting only as a client?
6. Does this change store Kakao API response data?
7. Does this change affect recommendation reproducibility?
8. Does this change affect RAG boundaries?
```

If any answer violates `AGENTS.md`, stop.

## H3. Plan Gate

Create a plan before editing.

For small tasks, a short plan is enough:

```text
Plan:
1. Inspect current files.
2. Make scoped change.
3. Run verification.
4. Report result.
```

For complex tasks, create an ExecPlan using:

```text
.agent/EXEC_PLAN_TEMPLATE.md
```

A complex task includes:

- DB schema creation
- migration generation
- admin permission model
- map-service canonical schema
- recommendation snapshot sync
- beverage catalog schema
- RAG knowledge-base schema
- Kakao API integration
- route optimization
- service-boundary refactor

## H4. Ownership Decision Matrix

Use this matrix before changing data flow.

| Data | Canonical Owner | Codex Rule |
|---|---|---|
| User identity | auth-service | Never duplicate auth ownership |
| Raw survey answers | survey-service | Recommendation may derive, not mutate |
| Taste profile | recommendation-service | Version mapper/vector changes |
| Places/venues | map-service/place-service | Canonical owner |
| Location/PostGIS geometry | map-service/place-service | Do not write from recommendation |
| Menu items | map-service/place-service | Admin writes through API |
| Inventory | map-service/place-service | TTL and confidence required |
| Price offers | map-service/place-service | TTL and confidence required |
| Recommendation logs | recommendation-service | Store snapshot revisions |
| Beverage knowledge | recommendation-service or catalog-service | Separate structured data from RAG |
| RAG chunks | knowledge owner | Do not use as ranking source |

## H5. Change Gate

Before editing, define the exact change set.

Allowed change examples:

```text
- Add map-place ownership documentation.
- Add additive migration for places table.
- Add admin API DTO for inventory update.
- Add snapshot sync table for recommendation read model.
```

Forbidden vague changes:

```text
- Improve database.
- Implement map service.
- Add recommendation system.
- Make admin work.
- Integrate Kakao.
```

If the task is vague, narrow it before implementation.

## H6. Database Harness

For schema work, Codex must produce:

```text
1. Table purpose
2. Canonical owner
3. Writer roles
4. Reader services
5. Required indexes
6. Required constraints
7. Lifecycle/status fields
8. Audit requirements
9. Migration direction
10. Rollback considerations
```

Database schema must support:

- soft deletion
- source tracking
- operator override
- owner change request
- audit logging
- location search with PostGIS where needed
- inventory/price freshness

For map/place DB, minimum conceptual groups are:

```text
places
place_source_refs
place_overrides
place_change_requests
place_audit_logs
venue_menu_items
venue_inventory_items
venue_price_offers
outdoor_spot_profiles
business_claims
```

## H7. API Harness

For API work, Codex must identify:

```text
1. Caller
2. Callee
3. Auth requirement
4. Role requirement
5. Request shape
6. Response shape
7. Error cases
8. Idempotency rule
9. Audit event
10. Test cases
```

Admin APIs must check:

- operator vs owner role
- place ownership/claim
- field-level permissions
- approval requirement for sensitive changes

Sensitive changes include:

- name change
- address change
- coordinate change
- business type change
- closure
- ownership transfer

## H8. Kakao API Harness

Before adding or modifying Kakao API usage, Codex must answer:

```text
1. Is this realtime lookup only?
2. Is any response data stored?
3. If stored, is legal/partnership approval documented?
4. Is source_policy captured?
5. Is Kakao data prevented from becoming canonical by default?
6. Is there a fallback when Kakao API is unavailable?
```

Default allowed use:

```text
- realtime search
- map display support
- external link / landing support
- operator verification support
```

Default disallowed use:

```text
- bulk place ingestion
- long-term storage of Local API response as canonical DB
- automatic reactivation of closed places
```

## H9. Recommendation Harness

For recommendation work, Codex must preserve these rules:

```text
- Ranking uses structured data and versioned scoring.
- RAG is not the ranking engine.
- Map-service data is consumed as a snapshot/read model.
- Recommendation logs store snapshot revisions.
- Explanations use deterministic reason codes.
```

When recommending where to buy or drink a selected beverage, support distinct
trade-off options:

```text
nearest_reasonable
best_price
balanced_best
```

Do not return three near-identical top-scoring options if the product
requirement asks for meaningful alternatives.

## H10. RAG Harness

For RAG work, Codex must separate:

```text
structured recommendation data
from
natural-language knowledge chunks
```

For assistant work, Codex must read:

```text
docs/assistant/assistant-architecture.md
docs/assistant/rag-policy.md
docs/assistant/prompt-contract.md
docs/assistant/response-schema.md
docs/assistant/evaluation-policy.md
```

RAG may answer:

- beverage explanation
- tasting notes
- category explanation
- drinking method
- pairing explanation
- general knowledge

RAG must not be the source of truth for:

- live inventory
- current price
- current business status
- live opening hours
- route time
- recommendation score

If retrieval confidence is below threshold, answer unknown.

Assistant responses must preserve:

```text
- deterministic recommendation-service ranking
- reason codes
- score breakdowns
- source metadata
- refusal state when app facts are insufficient
```

## H11. Verification Gate

Before final response, run relevant checks.

Examples:

```text
unit tests
integration tests
migration dry-run
schema validation
lint
typecheck
API contract tests
snapshot sync tests
permission tests
```

If scripts exist, prefer:

```text
scripts/codex-harness/verify-docs.sh
scripts/codex-harness/verify-boundaries.sh
scripts/codex-harness/verify-migrations.sh
```

If a check cannot be run, report:

```text
Not run: <check>
Reason: <reason>
```

## H12. Diff Review Gate

Before final response, Codex must inspect its own changes and check:

```text
1. Did I modify files outside scope?
2. Did I create a new ownership conflict?
3. Did I introduce direct cross-service DB access?
4. Did I make Kakao data canonical?
5. Did I skip auditability?
6. Did I skip freshness/TTL for price or inventory?
7. Did I change scoring without versioning?
8. Did I introduce RAG as ranking logic?
```

If any issue is found, fix before final response.

## H13. Final Report

Final response must include:

```text
Summary
Changed files
Verification
Risks / Follow-ups
```
