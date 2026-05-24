# Operations Runbooks

## Purpose

This document defines operator runbooks for the 70% production-readiness target
in `docs/plans/009.md`.

These runbooks only cover recommendation-owned state. They do not authorize
direct writes to survey-service, map-service, place-service, or auth-service
databases.

## Catalog Import Rollback

Use when a promoted beverage seed causes quality, display, or recommendation
issues.

1. Identify the last known good commit or seed candidate list.
2. Revert the catalog seed selection in `app/services/beverage_import.py` or set
   affected `beverage_items.active = false` through an approved
   recommendation-service operator path.
3. Re-run:

```bash
python3 -m app.tools.beverage_import --promote-seed
python3 -m app.tools.beverage_catalog_audit --database
```

4. Rebuild Qdrant because it is derived:

```bash
python3 -m app.tools.qdrant_rebuild --owner-type beverage_item --recreate
```

5. Verify:

```bash
RUN_DB_SMOKE=1 RUN_QDRANT_SMOKE=1 \
  bash scripts/codex-harness/verify-release-gate.sh
```

Rollback rule:

```text
Do not delete recommendation logs. Historical logs must remain explainable.
```

## Scoring Config Rollback

Use when a new scoring config produces worse evaluation or live behavior.

1. Set the active scoring config back to the previous approved version, such as
   `scoring_v1`, through an additive data/config change.
2. Do not edit historical recommendation result rows.
3. Re-run:

```bash
python3 -m app.tools.evaluate_drink_recommendations \
  --min-fixture-count 20 \
  --min-hit-rate 0.85 \
  --max-negative-violations 0 \
  --min-category-style-match-rate 0.65 \
  --min-reason-code-coverage 0.95 \
  --min-positive-above-negative-rate 0.9
```

4. Confirm new recommendation requests record the restored scoring config
   version.

Rollback rule:

```text
Never silently change `scoring_v1`; create or reactivate a versioned config.
```

## Qdrant Rebuild

Use when Qdrant is stale, corrupted, unavailable, or recreated.

1. Confirm PostgreSQL has active canonical vectors:

```bash
python3 -m app.tools.beverage_catalog_audit --database
```

2. Recreate the derived collection from PostgreSQL:

```bash
python3 -m app.tools.qdrant_rebuild --owner-type beverage_item --recreate
```

3. Run a no-force index pass to verify unchanged payloads skip:

```bash
python3 -m app.tools.qdrant_index --owner-type beverage_item
```

4. Query the rebuilt collection:

```bash
python3 -m app.tools.qdrant_index_smoke --owner-type beverage_item
```

Fallback rule:

```text
Beverage recommendation serving must remain PostgreSQL-hydrated and deterministic
when Qdrant is unavailable.
```

## Survey Sync Replay

Use when survey-service events fail or profile generation must be replayed.

1. Inspect `survey_sync_events` for retry/dead-letter state.
2. Fix the underlying contract, mapper, or data issue.
3. Reset only the affected recommendation-owned sync event state through an
   approved operator path.
4. Re-run the sync worker or local smoke:

```bash
python3 -m app.tools.survey_sync
python3 -m app.tools.survey_sync_smoke
```

Replay rule:

```text
Fetch canonical survey responses through survey-service APIs/events. Do not read
the survey-service database directly.
```

## Map Snapshot Replay

Use when map snapshot import misses or rejects venue/menu/inventory/price
updates.

1. Inspect `map_snapshot_sync_events` and `map_snapshot_sync_cursors`.
2. Confirm the source event contract matches
   `docs/recommendation/map-read-model.md`.
3. Reset only recommendation-owned cursor/event state through an approved
   operator path.
4. Re-run:

```bash
python3 -m app.tools.map_snapshot_sync
python3 -m app.tools.venue_recommendation_smoke
```

Replay rule:

```text
Map/place snapshots are derived read models. Do not read or mutate map-service
canonical tables.
```

## Stale Venue Data Handling

Use when venue recommendations depend on old inventory or price snapshots.

1. Confirm snapshot freshness in recommendation logs:
   - `place_revision`
   - `inventory_revision`
   - `price_revision`
   - snapshot synced time
2. If inventory or price is expired, exclude by default or mark uncertainty in
   the response according to `docs/recommendation/map-read-model.md`.
3. Trigger map snapshot sync or wait for the map-service replay feed.
4. Do not invent live inventory, price, route time, or business status.

Staleness rule:

```text
No fresh structured snapshot means no fresh venue availability or price claim.
```

## Operational Metrics Triage

Use when beta operators need a quick service health snapshot beyond liveness and
readiness.

1. Query:

```bash
python3 -m app.tools.operational_metrics_smoke
```

or call:

```text
GET /v1/operations/metrics
```

2. Investigate these first:
   - `catalog_audit_critical_count`
   - `recommendation_empty_rate`
   - `profile_missing_rate`
   - `survey_sync_max_lag_seconds`
   - `map_snapshot_sync_max_lag_seconds`
   - `qdrant_failed_point_count`

3. Use the relevant runbook above for rollback or replay.

Metrics rule:

```text
Operational metrics are advisory beta telemetry. PostgreSQL recommendation-owned
state remains canonical, and Qdrant remains rebuildable.
```
