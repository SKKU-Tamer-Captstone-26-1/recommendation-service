# AGENTS.md

This repository is worked on by Codex and other AI-assisted engineering tools.

Codex must follow this file before making any code, schema, migration, API, or
documentation changes.

## 1. Prime Directive

Do not optimize for fast code generation.

Optimize for:

- correct service ownership
- reproducible implementation
- small scoped changes
- explicit acceptance criteria
- clear rollback path
- testable database and API behavior
- no cross-service database coupling

When the task is ambiguous, stop and ask for clarification instead of inventing
architecture.

## 2. Required Harness

Before doing any non-trivial work, Codex must apply the workflow in:

```text
.agent/HARNESS.md
```

A task is non-trivial if it changes any of the following:

- database schema
- service boundary
- API contract
- authentication or authorization behavior
- map/place data ownership
- recommendation scoring
- RAG or knowledge-base behavior
- assistant behavior
- Kakao API usage
- admin workflow
- migration strategy

## 3. Required Reading Order

Before planning implementation, read these documents in order:

```text
README.md
docs/README.md
docs/architecture.md
docs/implementation-readiness.md
.agent/HARNESS.md
.agent/DOMAIN_BOUNDARIES.md
```

For map/place work, also read:

```text
docs/map-place/ownership.md
docs/map-place/database.md
docs/integrations/kakao-api-policy.md
```

For recommendation work, also read:

```text
docs/recommendation/map-read-model.md
docs/recommendation/recommendation-logic.md
docs/recommendation/sync-flow.md
```

For RAG/chatbot work, also read:

```text
.agent/DOMAIN_BOUNDARIES.md
docs/assistant/assistant-architecture.md
docs/assistant/rag-policy.md
docs/assistant/prompt-contract.md
docs/assistant/response-schema.md
docs/assistant/evaluation-policy.md
```

## 4. Service Ownership Rules

### 4.1 Auth Service

`auth-service` owns:

- users
- roles
- identity
- login state
- JWT/session issuance

Other services must not own authentication state.

Client-supplied `user_id` must not be trusted when an authenticated context
exists.

### 4.2 Admin Page

Admin Page is not a data owner.

Admin Page is a privileged UI client.

Admin Page must write through service APIs only.

Forbidden:

```text
Admin Page -> map DB direct UPDATE
Admin Page -> recommendation DB direct UPDATE
Admin Page -> auth DB direct UPDATE
```

Allowed:

```text
Admin Page -> auth-service
Admin Page -> map-service admin API
Admin Page -> recommendation/catalog admin API
```

### 4.3 Map / Place Service

`map-service` or `place-service` is the canonical owner of:

- places
- venues
- bars
- pubs
- liquor shops
- outdoor spots
- locations
- PostGIS geometry
- addresses
- business status
- publication status
- menu items
- signature menus
- inventory
- price offers
- business claims
- owner-submitted changes
- operator overrides
- place audit logs

All writes to place/menu/inventory/price data must go through map-service APIs
or map-service ingestion workers.

### 4.4 Recommendation Service

`recommendation-service` owns:

- user taste profiles derived from survey data
- curated MVP beverage catalog records and beverage flavor profiles until a
  separate catalog-service exists
- recommendation vectors
- vector schema versions
- mapper versions
- scoring configuration
- recommendation logs
- recommendation explanations
- map/place read-model snapshots used for ranking

`recommendation-service` must not:

- own authentication, OAuth, or JWT issuance
- write to map-service tables
- directly read map-service databases
- directly read survey-service databases
- treat map-service data as canonical recommendation-owned data
- decide whether a place exists canonically
- directly mutate menu, inventory, or price data
- rely on Qdrant as the only vector store
- treat Qdrant as canonical beverage catalog or vector storage

It may consume published map-service data through:

- internal APIs
- events
- snapshots
- sync jobs

PostgreSQL is canonical for recommendation-owned state. Qdrant is rebuildable
and disposable.

### 4.5 Survey Service

`survey-service` owns raw survey answers.

`recommendation-service` may derive taste profiles from survey outputs, but must
not own or mutate raw survey answers.

### 4.6 Chatbot / RAG

The ONTHEBLOCK assistant is an orchestration layer. It may use RAG for grounded
context and beverage knowledge, but it must not become a canonical data owner.

Chatbot/assistant must not use RAG or the LLM as the source of truth for:

- live place status
- inventory
- price
- business hours
- current availability
- recommendation score
- recommendation ranking

For recommendation questions, chatbot/assistant must call
`recommendation-service` and use deterministic recommendation results, score
breakdowns, reason codes, and snapshot metadata.

For live place/menu/inventory/price data outside recommendation snapshots,
chatbot/assistant must call approved service APIs or tools. It must never read
another service database directly.

## 5. Kakao API Policy

Kakao Local/Map API must not be treated as a canonical bulk-ingestion source
unless legal or partnership review explicitly allows it.

Default rule:

```text
Kakao API = realtime lookup / display / linking support
Our DB = operator curated / owner submitted / field researched / storage-permitted public data
```

Do not build features that store Kakao Local API response data long-term as
canonical place data without explicit approval.

If Kakao-derived data is temporarily referenced, it must be marked with source
policy metadata such as:

```text
source_type = KAKAO
source_policy = realtime_only | restricted | storable
```

## 6. Database Rules

Use PostgreSQL as the canonical database for owned relational state.

Use PostGIS for map/place spatial search.

Use soft delete or archival states for places.

Do not hard-delete business-critical records unless the task explicitly requires
it and documents why.

Required place lifecycle states include at minimum:

```text
active
hidden
closed
duplicate_merged
rejected
archived
```

Every table that receives admin/operator/owner writes must have:

- `created_at`
- `updated_at`
- actor or source metadata where applicable
- audit trail or event trail where applicable

## 7. Source Priority Rules

When external data, owner data, and operator data conflict, use this priority
order:

```text
1. operator_override
2. operator_verified
3. owner_verified
4. field_research
5. public_data
6. external_realtime_source
7. user_report_pending
```

If a place is already closed, archived, or duplicate-merged, ingestion must not
reactivate it automatically.

Use a review task instead.

```text
if place.status in ["closed", "archived", "duplicate_merged"]:
    ingestion_worker must not reactivate automatically
    create review_task instead
```

## 8. Recommendation Snapshot Rule

Recommendation results must be reproducible.

When recommending a place, store enough snapshot metadata to explain why it was
recommended later.

Recommendation logs should include:

- request_id
- user identity from auth context
- selected beverage if applicable
- recommended place id
- place revision
- inventory revision
- price revision
- score breakdown
- reason codes
- created_at

## 9. RAG Boundary Rule

RAG is for explanation and knowledge retrieval.

RAG must not be the ranking engine.

Recommendation ranking must use:

- structured profile data
- structured beverage data
- structured place/menu/inventory/price data
- vectors
- versioned scoring configuration

If RAG retrieval confidence is low, chatbot must say it does not know.

No retrieved evidence means no answer.

Assistant answers must be grounded in retrieved facts and must preserve internal
source metadata for traceability.

## 10. Planning Requirement

For complex features, migrations, refactors, or service-boundary changes, create
an ExecPlan using:

```text
.agent/EXEC_PLAN_TEMPLATE.md
```

The plan must be reviewed before implementation when the task affects:

- database schema
- API contract
- ownership boundaries
- production data
- Kakao API usage
- recommendation scoring
- admin permissions

## 11. Implementation Rules

Make the smallest useful change.

Do not introduce speculative infrastructure.

Do not add Kafka, Redis, Airflow, separate ML serving, or new services unless the
task explicitly requires it.

Prefer:

- additive migrations
- versioned schemas
- explicit constraints
- idempotent sync
- deterministic scoring
- deterministic reason codes

Avoid:

- cross-service DB joins
- hidden shared ownership
- unversioned mapper changes
- unversioned scoring changes
- unbounded LLM-generated explanations
- direct mutation of another service's state

## 12. Verification Rules

Before final response, Codex must run or explain the status of:

- relevant tests
- migration checks
- lint/type checks if available
- schema validation if relevant
- boundary verification if relevant

If scripts exist, prefer:

```text
scripts/codex-harness/verify-docs.sh
scripts/codex-harness/verify-boundaries.sh
scripts/codex-harness/verify-migrations.sh
```

If a check cannot be run, say why.

Never claim tests passed unless they were actually run.

## 13. Final Response Format

Every final response must include:

```text
Summary
Changed files
Verification
Risks / Follow-ups
```

If no code was changed, say so.

If the task only produced documentation, say so.
