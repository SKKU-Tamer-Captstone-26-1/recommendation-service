# Kakao API Policy

## Core Rule

Kakao Local/Map API must not be treated as canonical bulk-ingestion source
unless legal or partnership approval explicitly allows it.

Before implementation, any feature that stores Kakao-derived data MUST document
the storage policy, retention period, source metadata, and approval source.

## Allowed By Default

```text
- realtime lookup
- map display support
- external Kakao map link
- operator verification support
```

## Not Allowed By Default

```text
- bulk place ingestion
- storing Local API responses as canonical place data
- using Kakao result as permanent source of truth
- reactivating closed places based only on Kakao lookup
```

## Source Metadata

If Kakao-derived data is referenced, track policy metadata.

```text
source_type = KAKAO
source_policy = realtime_only | restricted | storable
source_observed_at = timestamp
source_expires_at = timestamp when applicable
```

## Preferred Canonical Sources

```text
1. operator curated data
2. owner submitted and verified data
3. field research
4. storage-permitted public data
5. external realtime lookup
```

## Route / Transit Limitation

Do not assume Kakao Local/Map API provides all route optimization needs.

MVP route strategy:

```text
Phase 1:
- straight-line distance
- approximate walking distance
- price
- inventory
- preference-based recommendation

Phase 2:
- external route provider or route module
- route_estimate_cache

Phase 3:
- public transit time
- transfers
- last train/bus
- walking distance
- route complexity scoring
```
