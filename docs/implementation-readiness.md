# Implementation Readiness

## Purpose

This document defines what must be true before real implementation starts.

It converts the architecture docs into implementation gates so Codex and future
contributors do not start coding from an ambiguous contract.

## Current Status

The repository is in pre-implementation contract mode.

Docs are the source of truth for:

- service ownership
- storage ownership
- API direction
- vector semantics
- sync and rebuild behavior
- assistant/RAG boundaries
- map/place snapshot boundaries

Implementation MUST follow these docs. If code and docs conflict, stop and fix
the docs or code before continuing.

## Repository Implementation Scope

This repository implements `recommendation-service`.

Allowed implementation scope:

- recommendation gRPC service
- operational FastAPI health/status endpoints
- PostgreSQL schema for recommendation-owned state
- Qdrant indexing client and rebuild flow
- survey-service gRPC client for profile generation
- map/place snapshot read model for venue recommendation
- deterministic recommendation pipeline
- deterministic explanation generation
- tests, migrations, and local Docker development

Out of scope for this repository unless a future decision says otherwise:

- auth-service implementation
- survey-service implementation
- map-service/place-service canonical database
- admin page implementation
- assistant-service production runtime
- LLM provider integration
- model training or fine-tuning
- Kakao bulk ingestion or long-term canonical storage

## Mandatory Implementation Gates

### Gate 1: Service Boundary

Before implementing a feature, identify the canonical data owner.

Rules:

- User identity comes from auth/gateway context.
- Raw survey answers come from `survey-service` APIs/events.
- Canonical place/menu/inventory/price data comes from map-service/place-service.
- Recommendation-owned data is stored in this service's PostgreSQL.
- Qdrant is rebuildable and never canonical.

### Gate 2: API Contract

Before implementing gRPC handlers:

- Confirm the protobuf package and service names.
- Do not generate code from temporary proto drafts.
- Do not accept client-supplied `user_id`.
- Include request IDs for traceability.
- Return typed profile states instead of ambiguous empty results.

### Gate 3: Database Contract

Before creating migrations:

- Read `database/erd.md`.
- Implement recommendation-owned tables only.
- Treat map/place data as snapshot/read-model tables.
- Add version tables before storing versioned artifacts.
- Store canonical vectors in PostgreSQL before Qdrant indexing.

### Gate 4: Sync Contract

Before implementing sync workers:

- Use service APIs/events only.
- Make processing idempotent.
- Persist cursor, attempts, retry time, and dead-letter state.
- Do not use 2PC or cross-service transactions.
- Keep rebuild possible from source services plus versioned metadata.

### Gate 5: Recommendation Contract

Before implementing scoring:

- Use deterministic candidate generation and reranking.
- Version scoring configs.
- Store score breakdowns and reason codes.
- Do not use RAG or an LLM for ranking.
- Make explanations reproducible from stored metadata.

### Gate 6: Assistant Contract

Assistant docs are design contracts, not implementation approval.

Before implementing assistant runtime:

- Decide whether assistant lives in this repo or a separate service.
- Finalize AssistantService protobuf workflow.
- Define LLM provider abstraction and secret handling.
- Add prompt version storage if prompts become runtime artifacts.
- Add no-answer and grounding evaluation tests.

Until then, assistant work should remain documentation, contract, or test-design
only.

### Gate 7: Verification Contract

Every implementation change must state which checks were run.

Expected checks by area:

| Area | Minimum Checks |
|---|---|
| config/app startup | import/startup tests, health checks |
| database | migration upgrade/downgrade or dry-run |
| sync | idempotency tests, retry/dead-letter tests |
| vector/Qdrant | rebuild/indexing tests |
| recommendation | deterministic ranking and explanation tests |
| assistant | grounding, refusal, and verifier tests |

## MVP Implementation Order

Recommended order:

1. Project package structure and typed configuration.
2. FastAPI health/status endpoints and gRPC server skeleton.
3. PostgreSQL connection, SQLAlchemy base, and Alembic.
4. Version registries: vector schema, mapper, scoring config.
5. Profile state, profile revisions, survey source snapshots, vectors.
6. Sync cursors, sync events, retry, and dead-letter tables.
7. Qdrant collection metadata and indexing client.
8. Survey-service client interface and pull-sync worker.
9. Beverage recommendation API and deterministic explanation templates.
10. Map/place snapshot read model and venue recommendation API.
11. Rebuild and recovery commands.
12. Assistant runtime only after a separate implementation decision.

## Decisions Required Before Coding Certain Areas

| Area | Required Decision |
|---|---|
| Protobuf | Final location and package for `recommendation.proto` |
| Identity | Exact gateway/auth metadata passed to gRPC handlers |
| Survey sync | SurveyService event/list/get response contract |
| Beverage catalog | Whether catalog remains in recommendation-service or moves later |
| Map snapshots | Map-service event/snapshot contract and freshness fields |
| Assistant | Separate service vs module, provider strategy, prompt storage |
| Kakao | Legal/partnership policy before storing Kakao response data |

## Do Not Implement Yet

Do not implement these until explicit approval:

- LLM-based assistant runtime
- RAG storage or vectorization
- fine-tuning or warm-up learning
- canonical map/place database
- canonical inventory/price writes
- direct survey database reads
- direct map database reads
- Kafka, Redis, Airflow, or distributed workflow systems
- route optimization beyond documented MVP approximations

## Update Rules

- Update this document when implementation order, gates, or scope changes.
- Keep detailed schema in `database/erd.md`.
- Keep recommendation scoring in `recommendation/recommendation-logic.md`.
- Keep assistant behavior in `assistant/`.
