# Recommendation Map Read Model

## Rule

Recommendation service must not own canonical map/place data.

It consumes published map-service data through:

- internal API
- events
- snapshots
- sync jobs

## Events / Sync Inputs

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

## Read Model Tables

```text
venue_snapshots
- place_id
- place_revision
- name
- place_type
- location
- status
- snapshot_json
- synced_at

venue_inventory_snapshots
- place_id
- beverage_id
- availability_status
- price_krw
- confidence
- last_seen_at
- synced_at
```

## Recommendation Logs

Recommendation logs must include snapshot revision data.

```text
recommendation_logs
- request_id
- user_id
- selected_beverage_id
- recommended_place_id
- place_revision
- inventory_revision
- price_revision
- score_breakdown_json
- reason_codes
- created_at
```

## Selected Beverage Purchase Options

When a user selects a beverage, recommendation should provide differentiated
options:

```text
nearest_reasonable
best_price
balanced_best
```

Scoring inputs may include:

- distance
- estimated travel time
- price
- availability confidence
- inventory freshness
- user taste profile
- venue quality
- route complexity

