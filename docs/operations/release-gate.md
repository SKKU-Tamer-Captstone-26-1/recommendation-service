# Release Gate

## Purpose

This document defines the local release gate for moving
`recommendation-service` toward the 70% production-readiness target in
`docs/plans/009.md`.

The gate is intentionally deterministic. PostgreSQL remains canonical, Qdrant is
treated as rebuildable, and recommendation quality is checked with catalog audit
and offline drink evaluation thresholds.

## Local Gate

Run:

```bash
bash scripts/codex-harness/verify-release-gate.sh
```

The default gate runs:

- `pytest`
- `ruff`
- `compileall`
- `git diff --check`
- beverage catalog audit
- drink recommendation evaluation thresholds
- code boundary scan for direct survey/map database access

## Optional Database Smoke

When a local PostgreSQL database is running and `DATABASE_URL` points to it:

```bash
RUN_DB_SMOKE=1 bash scripts/codex-harness/verify-release-gate.sh
```

This additionally runs:

```bash
python3 -m alembic upgrade head
```

## Optional Qdrant Rebuild Smoke

When PostgreSQL and Qdrant are both running:

```bash
RUN_DB_SMOKE=1 RUN_QDRANT_SMOKE=1 \
  bash scripts/codex-harness/verify-release-gate.sh
```

This additionally:

- imports/stages beverage candidates and promotes the reviewed MVP beverage seed
- re-runs seed promotion to prove idempotency
- audits active database beverages
- rebuilds the Qdrant beverage collection from PostgreSQL vectors
- runs a no-force Qdrant index pass to prove unchanged indexed points can skip
- queries Qdrant for an indexed beverage vector
- runs a beverage recommendation smoke proving serving still uses
  PostgreSQL-hydrated deterministic ranking after the Qdrant rebuild

## Rollback Notes

- Catalog rollback: restore the previous seed candidate list or deactivate newly
  promoted beverage rows.
- Qdrant rollback: disable Qdrant-backed retrieval and rebuild the collection
  from PostgreSQL vectors.
- Evaluation rollback: keep the stricter fixtures; lower thresholds only with an
  explicit product decision.

## Human-Required External Checks

The deployed survey-service and map-service smoke checks cannot be completed
until those deployed endpoints and auth metadata are available. Track that under
`docs/human-effort.md` if it blocks later plan slices.
