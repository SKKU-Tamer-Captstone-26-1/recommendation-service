# Production Metrics

## Purpose

This document defines the Plan 010 production metrics surface for
`recommendation-service`.

PostgreSQL remains canonical for recommendation-owned state. Metrics are
operational telemetry only.

## Endpoints

```text
GET /v1/operations/metrics
GET /v1/operations/metrics/prometheus
```

`/v1/operations/metrics` returns JSON for operators and smoke tests.

`/v1/operations/metrics/prometheus` returns Prometheus text format for scraping.

## Metric Groups

Operational state:

```text
recommendation_request_count
recommendation_empty_rate
recommendation_average_results_per_request
profile_missing_rate
profile_stale_count
survey_sync_max_lag_seconds
map_snapshot_sync_max_lag_seconds
catalog_audit_critical_count
qdrant_pending_point_count
qdrant_failed_point_count
db_pool_size
db_pool_checked_out
db_pool_checked_in
db_pool_overflow
```

Runtime telemetry:

```text
recommendation_runtime_latency_ms_bucket
recommendation_runtime_latency_ms_count
recommendation_runtime_latency_ms_sum
recommendation_grpc_status_total
```

## Suggested Alert Rules

Initial beta alerts:

```text
5m error_rate > 2%
10m p95 latency > 800ms
recommendation_empty_rate > 0.10
profile_missing_rate > 0.20
survey_sync_max_lag_seconds > 600
map_snapshot_sync_max_lag_seconds > 600
qdrant_failed_point_count > 0
catalog_audit_critical_count > 0
db_pool_checked_out approaches db_pool_size for 5m
```

## Grafana Dashboard Skeleton

Panels:

```text
1. Request rate by gRPC method
2. Error rate by gRPC method/status
3. Recommendation latency p50/p95/p99
4. Recommendation empty rate
5. Profile missing/stale rate
6. Survey sync lag
7. Map snapshot sync lag
8. Qdrant pending/failed points
9. DB pool checked out / size
10. Catalog audit critical/warning count
```

## Safety Rules

- Metrics exporter failure must not block recommendation serving.
- `/health/live` must remain dependency-free.
- Metrics must not include raw survey answers.
- Metrics must not expose user tokens or request payload secrets.
- Metrics must not require direct reads from survey-service or map-service
  databases.
