# Map / Place Ownership

## Core Decision

`map-service` or `place-service` is the canonical owner of place-related data.

Admin Page is not a data owner.

Recommendation service is not a data owner for place/menu/inventory/price data.

## Data Flow

```text
Kakao API / public data / field research / owner input
        |
        v
place-ingestion / admin APIs
        |
        v
map-service(place-service) DB
        |
        v
1. Map screen displays active/published places
2. Recommendation service consumes snapshot/read model
3. Chatbot calls map-service tool/API for live place data
```

## Clients

### Map Screen

Read-only client.

```text
Flutter/React map screen
  -> map-service public API
  -> active/published places only
```

### Admin Page

Write-capable privileged client.

```text
Admin Page
  -> auth-service for identity/roles
  -> map-service admin API for place/menu/inventory/price
  -> recommendation/catalog admin API for beverage knowledge if needed
```

### Recommendation Service

Read-only consumer.

```text
recommendation-service
  -> map-service internal API or event sync
  -> stores venue/menu/inventory snapshots
  -> uses snapshots for scoring
```

## Ownership Table

| Data | Canonical Owner | Readers | Writers |
|---|---|---|---|
| User account/role | auth-service | all services | auth-service |
| Place basic info | map-service | map, recommendation, chatbot | operator, approved owner, ingestion worker |
| Location/PostGIS geometry | map-service | map, recommendation | operator or verified source |
| Name/address/closure/merge | map-service | map, recommendation | operator first, owner via request |
| Signature menu | map-service | map, recommendation, chatbot | owner/operator |
| Inventory/availability | map-service | recommendation, map | owner/operator |
| Price | map-service | recommendation, map | owner/operator |
| Beverage knowledge | recommendation-service or catalog-service | recommendation, chatbot | operator/knowledge admin |
| Survey/taste | survey-service / recommendation-service | recommendation | survey/recommendation |
| Recommendation logs | recommendation-service | analytics/recommendation | recommendation |

## Operator Permissions

Operators may:

- create places
- hide places
- close places
- archive places
- merge duplicates
- force-edit business name
- edit address/location
- edit category
- invalidate owner data
- approve/reject business claims
- exclude a place from recommendation
- resolve source conflicts

## Owner Permissions

Owners may directly edit:

- inventory
- menu price
- signature menu
- menu description
- promotions
- temporary business hours
- representative images

Owners must request approval for:

- business name change
- address change
- coordinate change
- business type change
- closure
- ownership transfer

## Lifecycle

Places should use lifecycle states instead of hard delete.

```text
active
hidden
closed
duplicate_merged
rejected
archived
```

## Conflict Priority

```text
1. operator_override
2. operator_verified
3. owner_verified
4. field_research
5. public_data
6. external_realtime_source
7. user_report_pending
```

## Reactivation Rule

```text
if place.status in ["closed", "archived", "duplicate_merged"]:
    ingestion_worker must not reactivate automatically
    create review_task instead
```
