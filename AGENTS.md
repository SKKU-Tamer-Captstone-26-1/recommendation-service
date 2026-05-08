# Repository Agent Rules

## Purpose

This file is the root AI entry point for Codex, Cursor, Claude Code, and future
AI-assisted development tools.

AI agents MUST read this file before modifying code, tests, migrations,
configuration, or documentation.

## Why This File Exists

Root `AGENTS.md` defines repository-level engineering contracts.

It MUST document:

- AI behavior rules
- repository-level constraints
- required reading order
- safe change workflow
- root docs vs domain docs ownership
- environment and migration safety rules

It MUST NOT document:

- full API schemas
- full database schemas
- vector dimension tables
- detailed recommendation formulas
- raw survey answer schemas

## Required Reading

Before any change:

1. `README.md`
2. `docs/architecture.md`
3. The domain document related to the change
4. Existing code and tests in the touched area

Domain document map:

| Change Area | Required Docs |
|---|---|
| API | `docs/api/recommendation-api.md` |
| Database or migrations | `docs/database/erd.md`, `docs/database/migration-strategy.md` |
| Recommendation scoring | `docs/recommendation/recommendation-logic.md` |
| Vector changes | `docs/recommendation/vector-schema.md` |
| Survey mapping | `docs/recommendation/survey-mapping.md` |
| Survey sync or rebuild | `docs/recommendation/sync-flow.md` |
| Service boundaries | `docs/architecture.md`, `docs/decisions/adr-001-derived-state.md` |

## Non-Negotiable Engineering Rules

- MUST treat `recommendation-service` as a derived-state service.
- MUST NOT own authentication, OAuth, or JWT issuing.
- MUST NOT accept client-supplied `user_id` as identity.
- MUST derive user identity from JWT/gateway-authenticated context.
- MUST NOT access the `survey-service` database directly.
- MUST NOT store raw survey answers as canonical state.
- MUST communicate with `survey-service` through APIs/events only.
- MUST use gRPC for MSA service-to-service contracts unless a document states
  why HTTP is being used for a specific operational path.
- MUST treat PostgreSQL as canonical for recommendation-owned state.
- MUST treat Qdrant as rebuildable and disposable.
- MUST NOT rely on Qdrant as the only vector store.
- MUST NOT use distributed transactions or 2PC.
- MUST make sync processing idempotent.
- MUST version vector schemas, mapper logic, profile revisions, and scoring
  configs.
- MUST preserve full profile regeneration and rebuild paths.
- MUST keep V1 explanations deterministic and traceable.

## AI Behavior Conventions

When working in this repository:

- Read before editing.
- Prefer existing docs and local patterns over invention.
- Make small, coherent changes.
- Update docs with behavior changes.
- Keep implementation aligned with source-of-truth docs.
- Avoid speculative infrastructure.
- Do not introduce Kafka, Redis, Airflow, ML serving, or distributed workflow
  systems unless explicitly requested and documented.
- Do not add new top-level folders without a clear repository role.

## Engineering Rule Style

Use this vocabulary in documentation and code comments:

| Term | Meaning |
|---|---|
| `MUST` | Required for correctness, ownership, rebuildability, or safety |
| `MUST NOT` | Forbidden because it breaks a service contract |
| `SHOULD` | Recommended default; deviations need a reason |
| `MAY` | Allowed but optional |

Avoid vague rules:

```text
Handle properly
Make scalable
Use best practices
```

Prefer concrete rules:

```text
Persist failed sync events with attempt count, last error, and next retry time.
Create a new vector schema version when dimension meaning changes.
Store canonical vectors in PostgreSQL before indexing Qdrant.
```

## Repository Navigation Rules

Root files define repository contracts:

- `README.md`: navigation and development workflow
- `AGENTS.md`: AI and contributor behavior rules
- `.env.example`: environment variable contract
- `pyproject.toml`: Python tooling contract
- `docker-compose.yml`: local infrastructure contract

`docs/` defines domain contracts:

- architecture
- recommendation logic
- vector schema
- survey mapping
- sync and rebuild flow
- API contracts
- database model
- migration strategy
- architectural decisions

Do not duplicate domain rules in root files. Link to the owning doc.

## Environment Rules

- MUST keep `.env.example` free of secrets.
- MUST document every required environment variable in `.env.example`.
- MUST use gRPC service addresses for MSA service-to-service communication.
- MAY keep HTTP URLs for health, local debugging, or JWKS-style auth metadata.
- MUST NOT configure direct access to `auth-service` or `survey-service`
  databases.
- SHOULD keep local defaults compatible with Docker Compose.

## Migration Safety Rules

Before creating or editing migrations:

- Read `docs/database/erd.md`.
- Read `docs/database/migration-strategy.md`.
- Identify rebuild impact.
- Identify Qdrant indexing impact.
- Preserve existing profile revisions unless explicitly archived.
- Create new vector, mapper, or scoring versions instead of mutating semantics in
  place.

## Change Safety Checklist

Before finishing a change:

- Does it preserve service ownership?
- Does it keep PostgreSQL canonical?
- Can Qdrant be rebuilt from PostgreSQL?
- Is survey-service accessed only through APIs/events?
- Are profile/vector/mapper/scoring versions preserved?
- Are recommendation explanations reproducible?
- Are retries and failure states idempotent?
- Do docs need to be updated?
- Do tests or migration checks need to be added?
