from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock

LATENCY_BUCKETS_MS = (50, 100, 250, 500, 800, 1000, 2500, 5000)


@dataclass(frozen=True)
class RuntimeOperationSnapshot:
    count: int
    error_count: int
    total_latency_ms: float
    average_latency_ms: float | None
    max_latency_ms: float | None
    latency_bucket_counts: dict[str, int] = field(default_factory=dict)
    status_counts: dict[str, int] = field(default_factory=dict)


class RuntimeMetricsRegistry:
    """Process-local counters for lightweight beta operations visibility."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._count_by_operation: dict[str, int] = {}
        self._error_count_by_operation: dict[str, int] = {}
        self._latency_total_by_operation: dict[str, float] = {}
        self._latency_max_by_operation: dict[str, float] = {}
        self._latency_bucket_counts: dict[str, int] = {}
        self._status_counts: dict[str, int] = {}

    def record(
        self,
        operation: str,
        *,
        latency_ms: float,
        error: bool = False,
        status: str = "ok",
    ) -> None:
        with self._lock:
            self._count_by_operation[operation] = (
                self._count_by_operation.get(operation, 0) + 1
            )
            if error:
                self._error_count_by_operation[operation] = (
                    self._error_count_by_operation.get(operation, 0) + 1
                )
            self._latency_total_by_operation[operation] = (
                self._latency_total_by_operation.get(operation, 0.0) + latency_ms
            )
            self._latency_max_by_operation[operation] = max(
                self._latency_max_by_operation.get(operation, 0.0),
                latency_ms,
            )
            status_key = f"{operation}:{status.lower()}"
            self._status_counts[status_key] = self._status_counts.get(status_key, 0) + 1
            for bucket in LATENCY_BUCKETS_MS:
                if latency_ms <= bucket:
                    bucket_key = f"{operation}:{bucket}"
                    self._latency_bucket_counts[bucket_key] = (
                        self._latency_bucket_counts.get(bucket_key, 0) + 1
                    )

    def snapshot(self) -> dict[str, RuntimeOperationSnapshot]:
        with self._lock:
            operations = sorted(self._count_by_operation)
            return {
                operation: RuntimeOperationSnapshot(
                    count=count,
                    error_count=self._error_count_by_operation.get(operation, 0),
                    total_latency_ms=round(
                        self._latency_total_by_operation[operation],
                        3,
                    ),
                    average_latency_ms=round(
                        self._latency_total_by_operation[operation] / count,
                        3,
                    )
                    if count
                    else None,
                    max_latency_ms=round(
                        self._latency_max_by_operation.get(operation, 0.0),
                        3,
                    )
                    if count
                    else None,
                    latency_bucket_counts={
                        str(bucket): self._latency_bucket_counts.get(
                            f"{operation}:{bucket}",
                            0,
                        )
                        for bucket in LATENCY_BUCKETS_MS
                    },
                    status_counts={
                        key.removeprefix(f"{operation}:"): value
                        for key, value in sorted(self._status_counts.items())
                        if key.startswith(f"{operation}:")
                    },
                )
                for operation in operations
                for count in (self._count_by_operation[operation],)
            }


runtime_metrics = RuntimeMetricsRegistry()
