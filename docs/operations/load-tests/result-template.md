# Load Test Result

## Summary

```text
date:
environment:
git_sha:
profile:
target:
operator:
```

## Scenario

```text
method_mix:
rps:
duration:
safe_test_user:
selected_beverage_id:
mutation_enabled:
```

## Versions

```text
recommendation_service_version:
active_vector_schema:
active_survey_mapper:
active_scoring_config:
qdrant_collection:
```

## Results

```text
total_requests:
success_count:
error_count:
error_rate:
p50_latency_ms:
p95_latency_ms:
p99_latency_ms:
max_latency_ms:
```

## Operational Metrics Before

```text
recommendation_request_count:
recommendation_empty_rate:
profile_missing_rate:
survey_sync_max_lag_seconds:
map_snapshot_sync_max_lag_seconds:
qdrant_failed_point_count:
```

## Operational Metrics After

```text
recommendation_request_count:
recommendation_empty_rate:
profile_missing_rate:
survey_sync_max_lag_seconds:
map_snapshot_sync_max_lag_seconds:
qdrant_failed_point_count:
```

## Bottlenecks

```text
db_connection_saturation:
slow_queries:
qdrant_latency:
worker_impact:
error_types:
```

## Decision

```text
pass_or_fail:
safe_rps_for_current_deployment:
required_changes_before_next_profile:
rollback_or_followup:
```
