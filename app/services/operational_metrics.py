from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.models.catalog import BeverageItem
from app.models.enums import ProfileStatus, QdrantIndexStatus, SyncEventStatus
from app.models.profile import UserProfileState
from app.models.recommendation_event import RecommendationRequest, RecommendationResult
from app.models.sync import (
    DeadLetterEvent,
    MapSnapshotSyncCursor,
    MapSnapshotSyncEvent,
    SurveySyncCursor,
    SurveySyncEvent,
)
from app.models.vector import QdrantPoint
from app.services.beverage_catalog_audit import BeverageCatalogAuditService
from app.services.runtime_metrics import RuntimeOperationSnapshot, runtime_metrics

MetricValue = int | float | None


class OperationalMetricsRepository(Protocol):
    def recommendation_request_count(self) -> int: ...
    def recommendation_result_count(self) -> int: ...
    def empty_recommendation_request_count(self) -> int: ...
    def profile_state_count(self) -> int: ...
    def profile_state_count_by_status(self, status: str) -> int: ...
    def active_beverage_count(self) -> int: ...
    def qdrant_point_count_by_status(self, status: str) -> int: ...
    def survey_sync_event_count_by_status(self, status: str) -> int: ...
    def map_snapshot_sync_event_count_by_status(self, status: str) -> int: ...
    def dead_letter_event_count(self) -> int: ...
    def oldest_survey_cursor_synced_at(self) -> datetime | None: ...
    def oldest_map_snapshot_cursor_synced_at(self) -> datetime | None: ...


class CatalogAuditProvider(Protocol):
    def audit_active_catalog(self) -> Any: ...


@dataclass(frozen=True)
class OperationalMetricsSnapshot:
    generated_at: datetime
    metrics: dict[str, MetricValue]


class SqlOperationalMetricsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def recommendation_request_count(self) -> int:
        return self._count(RecommendationRequest)

    def recommendation_result_count(self) -> int:
        return self._count(RecommendationResult)

    def empty_recommendation_request_count(self) -> int:
        result_exists = exists().where(
            RecommendationResult.request_id == RecommendationRequest.id,
        )
        return self._count(RecommendationRequest, ~result_exists)

    def profile_state_count(self) -> int:
        return self._count(UserProfileState)

    def profile_state_count_by_status(self, status: str) -> int:
        return self._count(UserProfileState, UserProfileState.status == status)

    def active_beverage_count(self) -> int:
        return self._count(BeverageItem, BeverageItem.active.is_(True))

    def qdrant_point_count_by_status(self, status: str) -> int:
        return self._count(QdrantPoint, QdrantPoint.index_status == status)

    def survey_sync_event_count_by_status(self, status: str) -> int:
        return self._count(SurveySyncEvent, SurveySyncEvent.status == status)

    def map_snapshot_sync_event_count_by_status(self, status: str) -> int:
        return self._count(MapSnapshotSyncEvent, MapSnapshotSyncEvent.status == status)

    def dead_letter_event_count(self) -> int:
        return self._count(DeadLetterEvent)

    def oldest_survey_cursor_synced_at(self) -> datetime | None:
        return self._oldest_synced_at(SurveySyncCursor)

    def oldest_map_snapshot_cursor_synced_at(self) -> datetime | None:
        return self._oldest_synced_at(MapSnapshotSyncCursor)

    def _count(self, model: type[Any], *criteria: Any) -> int:
        statement = select(func.count()).select_from(model)
        for criterion in criteria:
            statement = statement.where(criterion)
        return int(self._session.scalar(statement) or 0)

    def _oldest_synced_at(self, model: type[Any]) -> datetime | None:
        return self._session.scalar(
            select(func.min(model.last_synced_at)).where(
                model.last_synced_at.is_not(None),
            ),
        )


class OperationalMetricsService:
    def __init__(
        self,
        repository: OperationalMetricsRepository,
        *,
        catalog_audit: CatalogAuditProvider | None = None,
        runtime_snapshot: dict[str, RuntimeOperationSnapshot] | None = None,
        extra_metrics: dict[str, MetricValue] | None = None,
    ) -> None:
        self._repository = repository
        self._catalog_audit = catalog_audit
        self._runtime_snapshot = runtime_snapshot
        self._extra_metrics = extra_metrics or {}

    @classmethod
    def from_session(cls, session: Session) -> OperationalMetricsService:
        return cls(
            SqlOperationalMetricsRepository(session),
            catalog_audit=BeverageCatalogAuditService(session),
            extra_metrics=_db_pool_metrics(session),
        )

    def snapshot(self, now: datetime | None = None) -> OperationalMetricsSnapshot:
        resolved_now = _aware(now or datetime.now(UTC))
        request_count = self._repository.recommendation_request_count()
        result_count = self._repository.recommendation_result_count()
        empty_request_count = self._repository.empty_recommendation_request_count()
        profile_state_count = self._repository.profile_state_count()
        profile_missing_count = self._repository.profile_state_count_by_status(
            ProfileStatus.MISSING.value,
        )
        metrics: dict[str, MetricValue] = {
            "recommendation_request_count": request_count,
            "recommendation_result_count": result_count,
            "recommendation_empty_request_count": empty_request_count,
            "recommendation_empty_rate": _rate(empty_request_count, request_count),
            "recommendation_average_results_per_request": _rate(
                result_count,
                request_count,
            ),
            "profile_state_count": profile_state_count,
            "profile_missing_count": profile_missing_count,
            "profile_missing_rate": _rate(profile_missing_count, profile_state_count),
            "profile_stale_count": self._repository.profile_state_count_by_status(
                ProfileStatus.STALE.value,
            ),
            "profile_failed_generation_count": (
                self._repository.profile_state_count_by_status(
                    ProfileStatus.FAILED_GENERATION.value,
                )
            ),
            "active_beverage_count": self._repository.active_beverage_count(),
            "qdrant_pending_point_count": self._repository.qdrant_point_count_by_status(
                QdrantIndexStatus.PENDING.value,
            ),
            "qdrant_failed_point_count": self._repository.qdrant_point_count_by_status(
                QdrantIndexStatus.FAILED.value,
            ),
            "survey_sync_pending_count": (
                self._repository.survey_sync_event_count_by_status(
                    SyncEventStatus.PENDING.value,
                )
            ),
            "survey_sync_retry_count": (
                self._repository.survey_sync_event_count_by_status(
                    SyncEventStatus.RETRY.value,
                )
            ),
            "survey_sync_dead_letter_count": (
                self._repository.survey_sync_event_count_by_status(
                    SyncEventStatus.DEAD_LETTER.value,
                )
                + self._repository.dead_letter_event_count()
            ),
            "map_snapshot_sync_pending_count": (
                self._repository.map_snapshot_sync_event_count_by_status(
                    SyncEventStatus.PENDING.value,
                )
            ),
            "map_snapshot_sync_retry_count": (
                self._repository.map_snapshot_sync_event_count_by_status(
                    SyncEventStatus.RETRY.value,
                )
            ),
            "map_snapshot_sync_dead_letter_count": (
                self._repository.map_snapshot_sync_event_count_by_status(
                    SyncEventStatus.DEAD_LETTER.value,
                )
            ),
            "survey_sync_max_lag_seconds": _lag_seconds(
                self._repository.oldest_survey_cursor_synced_at(),
                resolved_now,
            ),
            "map_snapshot_sync_max_lag_seconds": _lag_seconds(
                self._repository.oldest_map_snapshot_cursor_synced_at(),
                resolved_now,
            ),
        }
        metrics.update(_catalog_audit_metrics(self._catalog_audit))
        metrics.update(_runtime_metrics(self._runtime_snapshot))
        metrics.update(self._extra_metrics)
        return OperationalMetricsSnapshot(generated_at=resolved_now, metrics=metrics)


def _catalog_audit_metrics(
    catalog_audit: CatalogAuditProvider | None,
) -> dict[str, MetricValue]:
    if catalog_audit is None:
        return {
            "catalog_audit_critical_count": None,
            "catalog_audit_warning_count": None,
        }
    report = catalog_audit.audit_active_catalog()
    return {
        "catalog_audit_critical_count": int(report.critical_count),
        "catalog_audit_warning_count": int(report.warning_count),
    }


def _runtime_metrics(
    snapshot: dict[str, RuntimeOperationSnapshot] | None,
) -> dict[str, MetricValue]:
    resolved_snapshot = snapshot if snapshot is not None else runtime_metrics.snapshot()
    metrics: dict[str, MetricValue] = {}
    for operation, operation_snapshot in resolved_snapshot.items():
        prefix = f"runtime_{operation}"
        metrics[f"{prefix}_request_count"] = operation_snapshot.count
        metrics[f"{prefix}_error_count"] = operation_snapshot.error_count
        metrics[f"{prefix}_total_latency_ms"] = operation_snapshot.total_latency_ms
        metrics[f"{prefix}_average_latency_ms"] = (
            operation_snapshot.average_latency_ms
        )
        metrics[f"{prefix}_max_latency_ms"] = operation_snapshot.max_latency_ms
        for status, count in operation_snapshot.status_counts.items():
            metrics[f"{prefix}_status_{_metric_key(status)}_count"] = count
    return metrics


def render_prometheus_metrics(
    snapshot: OperationalMetricsSnapshot,
    *,
    service: str,
    environment: str,
    runtime_snapshot: dict[str, RuntimeOperationSnapshot] | None = None,
) -> str:
    labels = {
        "service": service,
        "environment": environment,
    }
    lines = [
        "# HELP recommendation_operational_metric "
        "Recommendation service operational metric.",
        "# TYPE recommendation_operational_metric gauge",
    ]
    for name, value in sorted(snapshot.metrics.items()):
        if value is None:
            continue
        metric_labels = {**labels, "name": name}
        lines.append(
            "recommendation_operational_metric"
            f"{_labels(metric_labels)} {_number(value)}",
        )

    resolved_runtime = runtime_snapshot if runtime_snapshot is not None else (
        runtime_metrics.snapshot()
    )
    lines.extend(
        [
            "# HELP recommendation_runtime_latency_ms "
            "Runtime operation latency histogram.",
            "# TYPE recommendation_runtime_latency_ms histogram",
        ],
    )
    for operation, item in sorted(resolved_runtime.items()):
        for bucket, count in sorted(
            item.latency_bucket_counts.items(),
            key=lambda pair: float(pair[0]),
        ):
            lines.append(
                "recommendation_runtime_latency_ms_bucket"
                f"{_labels({**labels, 'operation': operation, 'le': bucket})} {count}",
            )
        lines.append(
            "recommendation_runtime_latency_ms_bucket"
            f"{_labels({**labels, 'operation': operation, 'le': '+Inf'})} "
            f"{item.count}",
        )
        lines.append(
            "recommendation_runtime_latency_ms_count"
            f"{_labels({**labels, 'operation': operation})} {item.count}",
        )
        lines.append(
            "recommendation_runtime_latency_ms_sum"
            f"{_labels({**labels, 'operation': operation})} "
            f"{_number(item.total_latency_ms)}",
        )

    lines.extend(
        [
            "# HELP recommendation_grpc_status_total gRPC method status count.",
            "# TYPE recommendation_grpc_status_total counter",
        ],
    )
    for operation, item in sorted(resolved_runtime.items()):
        if not operation.startswith("grpc_"):
            continue
        method = operation.removeprefix("grpc_")
        for status, count in sorted(item.status_counts.items()):
            lines.append(
                "recommendation_grpc_status_total"
                f"{_labels({**labels, 'method': method, 'status': status})} {count}",
            )
    return "\n".join(lines) + "\n"


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _lag_seconds(last_synced_at: datetime | None, now: datetime) -> int | None:
    if last_synced_at is None:
        return None
    return max(0, int((now - _aware(last_synced_at)).total_seconds()))


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _db_pool_metrics(session: Session) -> dict[str, MetricValue]:
    bind = session.get_bind()
    pool = getattr(bind, "pool", None)
    if pool is None:
        return {}
    return {
        "db_pool_size": _call_pool_metric(pool, "size"),
        "db_pool_checked_out": _call_pool_metric(pool, "checkedout"),
        "db_pool_checked_in": _call_pool_metric(pool, "checkedin"),
        "db_pool_overflow": _call_pool_metric(pool, "overflow"),
    }


def _call_pool_metric(pool: Any, method: str) -> int | None:
    value = getattr(pool, method, None)
    if not callable(value):
        return None
    try:
        result = value()
    except NotImplementedError:
        return None
    if isinstance(result, int):
        return result
    return None


def _metric_key(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value)


def _labels(labels: dict[str, str]) -> str:
    rendered = ",".join(
        f'{key}="{_escape_label(value)}"' for key, value in sorted(labels.items())
    )
    return "{" + rendered + "}"


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _number(value: int | float) -> str:
    if isinstance(value, int):
        return str(value)
    return f"{value:.6g}"
