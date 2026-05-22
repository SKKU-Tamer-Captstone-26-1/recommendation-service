# Map / Place Database Model

## Purpose

This document defines the conceptual database structure for
map-service/place-service.

The goal is to support:

- map display
- admin management
- owner management
- menu management
- inventory management
- price management
- recommendation snapshots
- auditability
- source conflict resolution

## Core Tables

```text
places
- id
- place_type
- canonical_name
- normalized_name
- status
- location geography(Point, 4326)
- address
- created_by_source
- verified_level
- published_at
- created_at
- updated_at

place_source_refs
- id
- place_id
- source_type
- external_source_id
- source_url
- source_policy
- last_checked_at

place_overrides
- id
- place_id
- field_name
- override_value
- reason
- created_by_admin_id
- created_at

place_change_requests
- id
- place_id
- requested_by_user_id
- requester_role
- change_type
- payload_json
- status
- reviewed_by
- reviewed_at

place_audit_logs
- id
- actor_user_id
- actor_role
- action
- target_type
- target_id
- before_json
- after_json
- created_at
```

## Menu / Inventory / Price Tables

```text
venue_menu_items
- id
- place_id
- beverage_id nullable
- menu_name
- menu_type
- price_krw nullable
- is_signature
- description
- status
- source_type
- last_verified_at

venue_inventory_items
- id
- place_id
- beverage_id
- availability_status
- stock_confidence
- last_seen_at
- updated_by_role
- expires_at

venue_price_offers
- id
- place_id
- beverage_id nullable
- menu_item_id nullable
- price_krw
- price_type
- valid_from
- valid_until
- source_type
- confidence
```

## Outdoor Spots

Outdoor spots are not normal venues.

```text
place_type = outdoor_spot
```

Outdoor spots are operator-curated.

```text
outdoor_spot_profiles
- place_id
- allowed_activity_notes
- nearby_store_notes
- seating_level
- crowd_level
- restroom_available
- parking_available
- weather_sensitive
- policy_notes
```

## Inventory Freshness

Recommended confidence policy:

```text
updated <= 3 days: high confidence
updated <= 7 days: medium confidence
updated >= 30 days: low confidence or exclude from recommendation
```

## Required Index Concepts

```text
places.location                 -- PostGIS spatial index
places.status
places.place_type
places.normalized_name
place_source_refs.source_type
place_source_refs.external_source_id
venue_menu_items.place_id
venue_menu_items.beverage_id
venue_inventory_items.place_id
venue_inventory_items.beverage_id
venue_inventory_items.availability_status
venue_inventory_items.expires_at
venue_price_offers.place_id
venue_price_offers.beverage_id
venue_price_offers.valid_until
```

