from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class RuntimeOperationSnapshot:
    count: int
    error_count: int
    average_latency_ms: float | None
    max_latency_ms: float | None


class RuntimeMetricsRegistry:
    """Process-local counters for lightweight beta operations visibility."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._count_by_operation: dict[str, int] = {}
        self._error_count_by_operation: dict[str, int] = {}
        self._latency_total_by_operation: dict[str, float] = {}
        self._latency_max_by_operation: dict[str, float] = {}

    def record(
        self,
        operation: str,
        *,
        latency_ms: float,
        error: bool = False,
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

    def snapshot(self) -> dict[str, RuntimeOperationSnapshot]:
        with self._lock:
            operations = sorted(self._count_by_operation)
            return {
                operation: RuntimeOperationSnapshot(
                    count=count,
                    error_count=self._error_count_by_operation.get(operation, 0),
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
                )
                for operation in operations
                for count in (self._count_by_operation[operation],)
            }


runtime_metrics = RuntimeMetricsRegistry()
