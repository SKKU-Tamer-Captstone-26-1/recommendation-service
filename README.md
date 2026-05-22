# recommendation-service

| Area | Technology |
|---|---|
| Language | Python 3.12+ |
| Service Transport | gRPC |
| HTTP Health / Debug | FastAPI, Uvicorn |
| Data Validation / Config | Pydantic, Pydantic Settings |
| Database | PostgreSQL, PostGIS |
| ORM / Migrations | SQLAlchemy, Alembic |
| Vector Index | Qdrant |
| Inter-Service Clients | gRPC, HTTPX |
| Testing / Linting | Pytest, Ruff |
| Local Development | Docker, Docker Compose |

AI-first backend service for On the Block recommendations.

This repository owns derived recommendation state only. It generates taste
profiles, recommendation vectors, scoring metadata, explanations, and
recommendation logs from survey data owned by `survey-service`.

The platform is MSA-based and uses gRPC for service-to-service communication.
FastAPI remains in this repository for operational health/status endpoints and
local debugging only.

## Why This File Exists

Root `README.md` is the repository entry point for humans and AI systems.

It MUST document:

- what this repository is
- how to navigate it
- how to start development
- which files define engineering rules
- what belongs at the repository root vs `docs/`
- the minimum environment configuration contract

It MUST NOT document:

- full database schemas
- detailed recommendation formulas
- raw survey answer schemas
- service-private details from `auth-service` or `survey-service`

## System Boundaries

| Service | Owns |
|---|---|
| `auth-service` | Authentication, Google OAuth, JWT issuing, user identity |
| `survey-service` | Raw survey answers, survey schema, survey response revisions |
| `map-service` / `place-service` | Canonical place, menu, inventory, price, and location data |
| `recommendation-service` | Derived taste profiles, vectors, scoring metadata, explanations, recommendation logs |
| `assistant-service` | Future grounded conversational orchestration; not recommendation ranking |

Non-negotiable rules:

- PostgreSQL is canonical for recommendation-owned state.
- Qdrant is a rebuildable vector index.
- Eventual consistency is accepted.
- Distributed transactions and 2PC are forbidden.
- Shared database access across services is forbidden.
- Profile regeneration and full rebuild must always be possible.
- Map/place data is consumed by recommendation-service as snapshots/read models
  only.
- RAG/LLM output must not become the recommendation ranking engine.

## Repository Structure

Expected repository layout:

```text
recommendation-service/
- README.md
- AGENTS.md
- .agent/
- .env.example
- docker-compose.yml
- pyproject.toml
- app/
- tests/
- scripts/
- migrations/
- docs/
```

Current implementation may be added incrementally, but root-level contracts
should exist before application code.

## Root Files vs Domain Docs

Root-level files are repository contracts:

| File | Role |
|---|---|
| `README.md` | Human and AI entry point, setup map, repo navigation |
| `AGENTS.md` | Rules for Codex, Cursor, Claude Code, and future AI agents |
| `.agent/` | Codex harness, domain boundaries, planning templates, checklists |
| `.env.example` | Environment variable contract and safe local defaults |
| `pyproject.toml` | Python package, tooling, formatting, and test configuration |
| `docker-compose.yml` | Local infrastructure contract |

`docs/` contains domain and architecture source-of-truth documents:

- implementation readiness gates
- service architecture
- recommendation logic
- assistant design contracts
- map/place ownership and read-model rules
- vector schema
- survey mapping
- sync and rebuild flow
- Kakao API policy
- API contracts
- ERD and migration strategy
- architectural decisions

Do not duplicate domain specs in root files. Root files point to the right source
document.

## AI Navigation Flow

AI systems SHOULD read files in this order before making changes:

1. `AGENTS.md`
2. `README.md`
3. `docs/README.md`
4. `docs/architecture.md`
5. `docs/implementation-readiness.md`
6. The domain document related to the requested change
7. Existing code in the target module
8. Tests covering the target behavior

For recommendation logic changes, also read:

1. `docs/recommendation/vector-schema.md`
2. `docs/recommendation/survey-mapping.md`
3. `docs/recommendation/recommendation-logic.md`

For sync or rebuild changes, also read:

1. `docs/recommendation/sync-flow.md`
2. `docs/database/erd.md`
3. `docs/database/migration-strategy.md`

For assistant/chatbot changes, also read:

1. `docs/assistant/assistant-architecture.md`
2. `docs/assistant/rag-policy.md`
3. `docs/assistant/response-schema.md`

## Development Workflow

Expected local workflow after implementation exists:

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d postgres qdrant
alembic upgrade head
python -m app.grpc.main
uvicorn app.main:app --reload
```

Docker-only workflow:

```bash
docker compose run --rm api alembic upgrade head
docker compose up --build grpc api
```

Useful checks:

```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
curl http://localhost:8000/v1/status
grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check
```

## Environment Configuration

`.env.example` is the source of truth for required runtime configuration.

Rules:

- Secrets MUST NOT be committed.
- Local defaults SHOULD be safe and non-production.
- Environment names MUST be stable and descriptive.
- Service URLs MUST target service APIs, not service databases.
- gRPC addresses SHOULD be used for MSA service-to-service calls.
- JWT configuration MUST verify tokens issued by `auth-service`; this service
  MUST NOT issue JWTs.

## Repository Conventions

Recommended conventions for future implementation:

| Path | Role |
|---|---|
| `app/` | FastAPI application, service modules, repositories, recommendation logic |
| `tests/` | Unit, integration, contract, rebuild, and recommendation quality tests |
| `scripts/` | Operational scripts for seeding, backfills, rebuilds, and local utilities |
| `migrations/` | Alembic migrations and migration environment |
| `docs/` | Domain architecture and source-of-truth engineering specs |

Rules:

- Application code SHOULD follow the boundaries documented in `docs/architecture.md`.
- Database changes MUST be reflected in `docs/database/erd.md`.
- API changes MUST be reflected in `docs/api/recommendation-api.md`.
- Vector, mapper, and scoring changes MUST be versioned and documented.
- Scripts that mutate data MUST be idempotent or explicitly document why they are
  one-time operations.
- Tests SHOULD cover rebuildability, sync idempotency, and explanation
  reproducibility.

## AI-First Repository Standards

This repository is optimized for AI-assisted backend development.

AI systems SHOULD:

- start from root `AGENTS.md`
- use `/docs` as domain source of truth
- inspect existing code before proposing changes
- keep edits narrow and traceable
- update docs when behavior changes
- preserve service ownership boundaries

AI systems MUST NOT:

- invent direct database access to other services
- bypass versioned vector, mapper, or scoring metadata
- make Qdrant canonical
- add speculative infrastructure
- hide recommendation behavior only in code

## Documentation Standards

- Use Markdown with stable headings.
- Use `MUST`, `MUST NOT`, `SHOULD`, and `MAY` for engineering rules.
- Keep source-of-truth statements in one file and link to them.
- Update docs in the same change as API, schema, vector, mapper, scoring, sync,
  or rebuild behavior.
- Do not add process-heavy documentation unless it prevents real engineering
  ambiguity.

## Source Documents

Start with:

- `AGENTS.md`
- `docs/README.md`
- `docs/architecture.md`
- `docs/implementation-readiness.md`
- `docs/recommendation/recommendation-logic.md`
- `docs/recommendation/vector-schema.md`
- `docs/recommendation/sync-flow.md`
- `docs/database/erd.md`
