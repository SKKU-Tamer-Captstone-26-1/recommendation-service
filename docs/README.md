# Domain Documentation

## Purpose

This directory contains domain-level source-of-truth documentation for the On the
Block `recommendation-service`.

Root-level files define repository contracts. Files under `docs/` define
architecture, recommendation behavior, API contracts, storage, sync, rebuild, and
decisions.

## Document Contract

### Why This File Exists

- Provides the index and reading order for domain documentation.
- Defines domain documentation standards for humans and AI systems.
- Separates source-of-truth documents from generated or temporary notes.

### What MUST Be Documented Here

- Domain documentation map.
- Source-of-truth document list.
- AI-friendly formatting conventions.
- Cross-document consistency rules.
- Update rules for documentation changes.

### What MUST NOT Be Documented Here

- Repository setup workflow. Use root `README.md`.
- AI behavior rules. Use root `AGENTS.md`.
- Environment variable contract. Use root `.env.example`.
- Python tooling configuration. Use root `pyproject.toml` when present.

### Recommended Sections

1. Purpose
2. Root vs Domain Docs
3. System Constraints
4. Source-of-Truth Documents
5. Reading Order
6. Folder Structure
7. AI-Friendly Formatting
8. Documentation Standards
9. Update Rules

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

## Root vs Domain Docs

Root files are repository contracts:

| File | Role |
|---|---|
| `../README.md` | Repository entry point and development workflow |
| `../AGENTS.md` | AI behavior and repository engineering rules |
| `../.env.example` | Environment variable contract |
| `../pyproject.toml` | Python tooling contract when implementation exists |
| `../docker-compose.yml` | Local infrastructure contract when implementation exists |

Domain docs live here:

- architecture
- recommendation logic
- vector schema
- survey mapping
- sync and rebuild flow
- API contracts
- database model
- migration strategy
- architectural decisions

## Source-of-Truth Documents

| Area | Source Document |
|---|---|
| Agent behavior | `../AGENTS.md` |
| Repository entry point | `../README.md` |
| Architecture and ownership | `architecture.md` |
| Recommendation pipeline | `recommendation/recommendation-logic.md` |
| Vector schema | `recommendation/vector-schema.md` |
| Survey-to-profile mapping | `recommendation/survey-mapping.md` |
| Survey sync and regeneration | `recommendation/sync-flow.md` |
| API contracts | `api/recommendation-api.md` |
| PostgreSQL and Qdrant metadata model | `database/erd.md` |
| Migration rules | `database/migration-strategy.md` |
| Derived-state decision | `decisions/adr-001-derived-state.md` |

## Reading Order

For a new human or AI contributor:

1. `../AGENTS.md`
2. `../README.md`
3. `architecture.md`
4. `recommendation/sync-flow.md`
5. `database/erd.md`
6. `recommendation/vector-schema.md`
7. `recommendation/survey-mapping.md`
8. `recommendation/recommendation-logic.md`
9. `api/recommendation-api.md`
10. `database/migration-strategy.md`
11. `decisions/adr-001-derived-state.md`

## Folder Structure

```text
docs/
├── README.md
├── architecture.md
├── recommendation/
│   ├── recommendation-logic.md
│   ├── vector-schema.md
│   ├── survey-mapping.md
│   └── sync-flow.md
├── api/
│   └── recommendation-api.md
├── database/
│   ├── erd.md
│   └── migration-strategy.md
└── decisions/
    └── adr-001-derived-state.md
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
