# Recommendation Map Read Model

## Purpose

This document defines how `recommendation-service` consumes map/place data for
venue recommendations without owning canonical place, menu, inventory, price, or
location state.

## Core Rule

`recommendation-service` stores map/place data only as derived snapshots/read
models.

Canonical ownership remains with map-service/place-service.

## Document Contract

### What MUST Be Documented Here

- Map/place ownership boundary.
- Snapshot sync inputs.
- Recommendation-owned read-model tables.
- Freshness and confidence rules.
- Required recommendation log metadata.
- Purchase-option output strategy.

### What MUST NOT Be Documented Here

- Canonical map-service schema. Use `../map-place/database.md`.
- Map-service admin workflow.
- Full recommendation scoring formula. Use `recommendation-logic.md`.
- Assistant response schema. Use `../assistant/response-schema.md`.

## Allowed Inputs

Recommendation may consume published map/place data through:

- internal gRPC APIs
- durable events
- signed snapshots
- scheduled sync jobs

Forbidden:

- direct map-service database reads
- direct map-service database writes
- treating snapshots as canonical place truth
- reactivating, closing, merging, or editing places

## Events / Sync Inputs

Minimum event types:

```text
place.published
place.updated
place.hidden
place.closed
place.merged
menu.updated
inventory.updated
price.updated
```

Each event SHOULD include:

```json
{
  "event_id": "map_evt_123",
  "event_type": "inventory.updated",
  "occurred_at": "2026-05-22T09:00:00Z",
  "place_id": "place_123",
  "place_revision": "place_rev_12",
  "inventory_revision": "inv_rev_8",
  "price_revision": "price_rev_3"
}
```

## Read-Model Tables

Read-model table definitions are owned by `../database/erd.md`.

Required conceptual tables:

```text
venue_snapshots
venue_menu_snapshots
venue_inventory_snapshots
venue_price_snapshots
map_snapshot_sync_cursors
map_snapshot_sync_events
```

These tables MUST include:

- external map/place identifiers
- source revision IDs
- snapshot payload or hash
- sync timestamp
- freshness or expiry metadata
- confidence metadata when source data is uncertain

`map_snapshot_sync_*` tables store recommendation-service sync cursors, event
payloads, retry state, and idempotency keys. They are not canonical map/place
tables.

## Freshness Policy

Venue recommendations MUST consider freshness.

Recommended MVP policy:

| Data | Fresh | Stale | Exclude By Default |
|---|---:|---:|---:|
| inventory | <= 3 days | > 7 days | >= 30 days |
| price | valid_until not expired | expired or unknown | expired by > 30 days |
| place status | latest revision | unknown revision | hidden, closed, merged |

Stale data MAY be returned only when the response clearly marks uncertainty and
the scoring config permits it.

## Venue Recommendation Facts

Venue recommendation results SHOULD expose:

- place id
- place name
- place type
- distance meters
- estimated travel time if available
- route complexity if available
- beverage id or selected item id
- availability status
- inventory confidence
- price
- price confidence
- place revision
- inventory revision
- price revision
- snapshot synced time
- freshness status

## Recommendation Logs

Recommendation logs MUST include snapshot revision data.

```text
recommendation_requests
- request_id
- external_user_id from auth context
- profile_revision_id
- selected_beverage_id if applicable
- request_context_json
- created_at

recommendation_results
- request_id
- rank
- target_type
- target_id
- recommended_place_id
- place_revision
- inventory_revision
- price_revision
- score_breakdown_json
- reason_codes
- created_at
```

Logs MUST preserve enough metadata to explain why a venue was recommended later,
even if map-service later updates the canonical place.

## Selected Beverage Purchase Options

When a user selects a beverage, recommendation should provide differentiated
options:

```text
nearest_reasonable
best_price
balanced_best
```

Scoring inputs may include:

- taste match
- distance
- estimated travel time
- route complexity
- price
- availability confidence
- inventory freshness
- price freshness
- venue quality

Do not return several near-identical top-scoring venues when the product request
expects meaningful alternatives.

MVP selected-beverage venue recommendations use straight-line distance labeled
as `distance_strategy = straight_line_mvp`. Route optimization and transit
estimates require a later approved slice.

## Rebuild Strategy

Map/place read models are rebuildable.

Rebuild source priority:

1. map-service/place-service snapshot API
2. map-service/place-service event replay
3. latest approved export from map-service/place-service

Qdrant venue/menu vectors MUST be rebuilt from PostgreSQL read-model snapshots
and canonical recommendation vectors, not from Qdrant payloads.

## Update Rules

- Update this document when map-service event contracts, freshness policy,
  snapshot fields, or venue recommendation tradeoffs change.
- Update `../database/erd.md` before creating migrations for read-model tables.
- Update `recommendation-logic.md` when freshness or confidence affects scoring.
