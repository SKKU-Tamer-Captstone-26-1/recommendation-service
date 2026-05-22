# Domain Documentation

## Purpose

This directory contains domain-level source-of-truth documentation for the On the
Block recommendation platform and `recommendation-service`.

Root-level files define repository contracts. Files under `docs/` define
architecture, recommendation behavior, assistant behavior, API contracts,
storage, sync, rebuild, and decisions.

The `.agent/` directory defines the required Codex harness for non-trivial work.

## Document Contract

### Why This File Exists

- Provides the index and reading order for domain documentation.
- Defines domain documentation standards for humans and AI systems.
- Separates source-of-truth documents from generated or temporary notes.

### What MUST Be Documented Here

- Domain documentation map.
- Source-of-truth document list.
- Harness document list.
- AI-friendly formatting conventions.
- Cross-document consistency rules.
- Update rules for documentation changes.

### What MUST NOT Be Documented Here

- Repository setup workflow. Use root `README.md`.
- AI behavior rules. Use root `AGENTS.md`.
- Environment variable contract. Use root `.env.example`.
- Python tooling configuration. Use root `pyproject.toml` when present.
- Runtime implementation details. Use code and API docs.

### Recommended Sections

1. Purpose
2. Root vs Domain Docs
3. Harness Docs
4. System Constraints
5. Source-of-Truth Documents
6. Reading Order
7. Folder Structure
8. AI-Friendly Formatting
9. Documentation Standards
10. Update Rules

### Engineering Constraints

- Documentation must preserve service boundaries.
- Documents must be short enough to keep current.
- Every versioned recommendation artifact must be traceable.
- Generated artifacts must not become source of truth.

### Update Rules

- Update this file when docs are added, removed, or renamed.
- Do not add new documentation processes without a clear implementation need.
- Keep this file concise and navigational.

## System Constraints

These rules are non-negotiable for implementation:

- `auth-service` owns authentication, Google OAuth, JWT issuing, and user identity.
- `survey-service` owns raw survey answers and survey schema.
- `recommendation-service` owns derived recommendation state only.
- PostgreSQL is the canonical source of truth for recommendation-owned state.
- Qdrant is a rebuildable derived vector index.
- Eventual consistency is accepted.
- Distributed transactions and 2PC are forbidden.
- Shared database access between services is forbidden.
- Taste profiles, vectors, mappers, and scoring configs must be versioned.
- Profile regeneration and full rebuild must always be possible.
- Recommendation explanations must be deterministic and auditable in V1.
- Assistant answers must be grounded in retrieved app facts.
- LLMs must not rank beverages, venues, stores, or bars.
- Admin Page is a privileged client, not a data owner.
- map-service/place-service owns canonical place/menu/inventory/price/location
  data.
- recommendation-service consumes map/place data as snapshots/read models only.
- Kakao API is realtime lookup/display/linking support only unless storage is
  explicitly approved.
- RAG must not be used as the recommendation ranking engine.
- No retrieved assistant evidence means no assistant answer.

## Root vs Domain Docs

Root files are repository contracts:

| File | Role |
|---|---|
| `../README.md` | Repository entry point and development workflow |
| `../AGENTS.md` | AI behavior and repository engineering rules |
| `../.env.example` | Environment variable contract |
| `../pyproject.toml` | Python tooling contract when implementation exists |
| `../docker-compose.yml` | Local infrastructure contract when implementation exists |

Harness files are Codex execution contracts:

| File | Role |
|---|---|
| `../.agent/HARNESS.md` | Required working loop for non-trivial Codex tasks |
| `../.agent/DOMAIN_BOUNDARIES.md` | Cross-service ownership boundaries |
| `../.agent/EXEC_PLAN_TEMPLATE.md` | Decision-complete implementation plan template |
| `../.agent/CODEX_TASK_TEMPLATE.md` | Reusable Codex task prompt template |
| `../.agent/ACCEPTANCE_CHECKLIST.md` | Completion checklist for boundary-safe work |

Domain docs live here:

- architecture
- map/place ownership and conceptual database model
- recommendation logic
- recommendation map read model
- assistant architecture, RAG policy, prompt contract, response schema, and
  evaluation policy
- vector schema
- survey mapping
- sync and rebuild flow
- Kakao integration policy
- API contracts
- database model
- migration strategy
- architectural decisions

## Source-of-Truth Documents

| Area | Source Document |
|---|---|
| Agent behavior | `../AGENTS.md` |
| Codex harness | `../.agent/HARNESS.md` |
| Domain boundaries | `../.agent/DOMAIN_BOUNDARIES.md` |
| Repository entry point | `../README.md` |
| Architecture and ownership | `architecture.md` |
| Map/place ownership | `map-place/ownership.md` |
| Map/place conceptual database | `map-place/database.md` |
| Recommendation pipeline | `recommendation/recommendation-logic.md` |
| Recommendation map read model | `recommendation/map-read-model.md` |
| Assistant architecture | `assistant/assistant-architecture.md` |
| Assistant RAG and no-hallucination policy | `assistant/rag-policy.md` |
| Assistant prompt contract | `assistant/prompt-contract.md` |
| Assistant response schema | `assistant/response-schema.md` |
| Assistant evaluation policy | `assistant/evaluation-policy.md` |
| Vector schema | `recommendation/vector-schema.md` |
| Survey-to-profile mapping | `recommendation/survey-mapping.md` |
| Survey sync and regeneration | `recommendation/sync-flow.md` |
| Kakao API policy | `integrations/kakao-api-policy.md` |
| API contracts | `api/recommendation-api.md` |
| PostgreSQL and Qdrant metadata model | `database/erd.md` |
| Migration rules | `database/migration-strategy.md` |
| Derived-state decision | `decisions/adr-001-derived-state.md` |

## Reading Order

For a new human or AI contributor:

1. `../AGENTS.md`
2. `../README.md`
3. `../.agent/HARNESS.md`
4. `../.agent/DOMAIN_BOUNDARIES.md`
5. `architecture.md`
6. `recommendation/sync-flow.md`
7. `database/erd.md`
8. `recommendation/vector-schema.md`
9. `recommendation/survey-mapping.md`
10. `recommendation/recommendation-logic.md`
11. `api/recommendation-api.md`
12. `database/migration-strategy.md`
13. `decisions/adr-001-derived-state.md`

For map/place work, also read:

1. `map-place/ownership.md`
2. `map-place/database.md`
3. `integrations/kakao-api-policy.md`

For recommendation work involving places, also read:

1. `recommendation/map-read-model.md`
2. `map-place/ownership.md`

For assistant/chatbot work, also read:

1. `assistant/assistant-architecture.md`
2. `assistant/rag-policy.md`
3. `assistant/prompt-contract.md`
4. `assistant/response-schema.md`
5. `assistant/evaluation-policy.md`
6. `recommendation/recommendation-logic.md`
7. `recommendation/map-read-model.md`

## Folder Structure

```text
docs/
- README.md
- architecture.md
- assistant/
  - assistant-architecture.md
  - rag-policy.md
  - prompt-contract.md
  - response-schema.md
  - evaluation-policy.md
- map-place/
  - ownership.md
  - database.md
- recommendation/
  - map-read-model.md
  - recommendation-logic.md
  - vector-schema.md
  - survey-mapping.md
  - sync-flow.md
- integrations/
  - kakao-api-policy.md
- api/
  - recommendation-api.md
- database/
  - erd.md
  - migration-strategy.md
- decisions/
  - adr-001-derived-state.md
```

Harness structure:

```text
.agent/
- HARNESS.md
- DOMAIN_BOUNDARIES.md
- EXEC_PLAN_TEMPLATE.md
- CODEX_TASK_TEMPLATE.md
- ACCEPTANCE_CHECKLIST.md
```

## AI-Friendly Formatting

- Use Markdown headings with stable names.
- Use `MUST`, `MUST NOT`, `SHOULD`, and `MAY` for engineering rules.
- Prefer tables for ownership, APIs, dimensions, statuses, and lifecycle states.
- Use fenced code blocks for payload examples and diagrams.
- Keep examples realistic but minimal.
- Cross-link related documents by path.
- Keep source-of-truth statements in exactly one document and reference them
  elsewhere.

## Documentation Standards

- Documents describe durable rules, not transient implementation guesses.
- Every document must state what it owns and what it does not own.
- Every schema, vector, mapper, and scoring change must identify rebuild impact.
- Do not duplicate table definitions, endpoint schemas, or vector dimensions across
  documents.
- If implementation contradicts documentation, update the documentation or fix the
  implementation before merging.

## Generated Artifacts

Generated artifacts are optional and must not be treated as source of truth.

Examples:

- Rendered ERD images.
- OpenAPI bundles generated from code.
- Schema diff reports.
- Qdrant collection inspection output.

If added later, place generated artifacts under `docs/generated/`.
