# ADR-001: Recommendation Service Is Derived-State Only

## Status

Accepted

## Purpose

This ADR records the core architectural decision that `recommendation-service`
owns only derived recommendation state.

## Document Contract

### Why This File Exists

- Makes the most important service boundary explicit and durable.
- Prevents future implementation from absorbing auth or survey ownership.
- Anchors rebuild, sync, and storage design.

### What MUST Be Documented Here

- Decision context.
- Accepted decision.
- Consequences.
- Forbidden alternatives.
- Impacted source-of-truth docs.

### What MUST NOT Be Documented Here

- Full database schema.
- Full API details.
- Detailed ranking formulas.
- Temporary implementation tasks.

### Recommended Sections

1. Status
2. Context
3. Decision
4. Consequences
5. Alternatives Rejected
6. Impacted Docs
7. Update Rules

### Engineering Constraints

- This decision MUST be treated as a root architectural constraint.
- Changes to this decision require a new ADR.
- Implementation must align with this decision before merge.

### Update Rules

- Do not rewrite accepted decision history.
- Add amendments only if they clarify without changing the decision.
- Create a new ADR if ownership changes.

## Context

The On the Block platform has separate services:

- `auth-service`
- `gateway-service`
- `survey-service`
- `recommendation-service`

`survey-service` is already implemented and deployed independently. It owns raw
survey answers and survey schema evolution.

The recommendation engine needs survey-derived taste profiles, recommendation
vectors, Qdrant indexing, scoring metadata, and recommendation logs. These must
be reproducible and rebuildable.

## Decision

`recommendation-service` owns derived recommendation state only.

It owns:

- derived taste profiles
- profile revisions
- recommendation vectors
- vector schema versions
- mapper versions
- scoring configs
- recommendation logs
- explanation metadata
- Qdrant indexing metadata
- sync cursors and failure state

It does not own:

- authentication
- JWT issuing
- Google OAuth
- raw survey answers
- survey schema source of truth
- survey database tables

## Consequences

- PostgreSQL is canonical for recommendation-owned state.
- Qdrant is a rebuildable derived vector index.
- Survey data is obtained through service APIs/events, not shared databases.
- Profile generation is eventually consistent.
- Distributed transactions and 2PC are forbidden.
- Every generated profile must record source survey identifiers and generation
  versions.
- Full rebuild must be possible from `survey-service` data plus versioned
  recommendation metadata.

## Alternatives Rejected

### Shared Survey Database Access

Rejected because it violates service ownership and couples deployment, schema,
and operational recovery across services.

### Recommendation Service Owns Survey Answers

Rejected because raw survey answers already belong to `survey-service`, and dual
ownership would make rebuilds and compliance harder.

### Qdrant As Canonical Vector Store

Rejected because Qdrant should be disposable and rebuildable. PostgreSQL must
store canonical recommendation vectors and indexing metadata.

### Distributed Transactions Across Services

Rejected because eventual consistency is sufficient and simpler. Idempotent sync
with retries is the required pattern.

## Impacted Docs

- `docs/architecture.md`
- `docs/recommendation/sync-flow.md`
- `docs/recommendation/survey-mapping.md`
- `docs/database/erd.md`
- `docs/database/migration-strategy.md`

