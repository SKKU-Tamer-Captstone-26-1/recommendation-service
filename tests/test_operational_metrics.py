import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.api import operations
from app.core.logging import JsonLogFormatter
from app.db.session import get_db
from app.main import app
from app.services.operational_metrics import (
    OperationalMetricsService,
    OperationalMetricsSnapshot,
)
from app.services.runtime_metrics import RuntimeOperationSnapshot


def test_operational_metrics_snapshot_calculates_beta_health_metrics() -> None:
    now = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)
    service = OperationalMetricsService(
        _FakeOperationalMetricsRepository(now),
        catalog_audit=_FakeCatalogAudit(critical_count=0, warning_count=2),
        runtime_snapshot={
            "beverage_recommendation": RuntimeOperationSnapshot(
                count=4,
                error_count=1,
                average_latency_ms=12.5,
                max_latency_ms=25.0,
            ),
        },
    )

    snapshot = service.snapshot(now)

    assert snapshot.metrics["recommendation_request_count"] == 10
    assert snapshot.metrics["recommendation_empty_rate"] == 0.2
    assert snapshot.metrics["recommendation_average_results_per_request"] == 3.0
    assert snapshot.metrics["profile_missing_rate"] == 0.25
    assert snapshot.metrics["survey_sync_max_lag_seconds"] == 300
    assert snapshot.metrics["map_snapshot_sync_max_lag_seconds"] == 900
    assert snapshot.metrics["catalog_audit_critical_count"] == 0
    assert snapshot.metrics["catalog_audit_warning_count"] == 2
    assert snapshot.metrics["runtime_beverage_recommendation_request_count"] == 4
    assert snapshot.metrics["runtime_beverage_recommendation_error_count"] == 1
    assert (
        snapshot.metrics["runtime_beverage_recommendation_average_latency_ms"] == 12.5
    )


def test_operations_metrics_endpoint_returns_flat_metrics(monkeypatch) -> None:
    generated_at = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)

    class _FakeService:
        def snapshot(self) -> OperationalMetricsSnapshot:
            return OperationalMetricsSnapshot(
                generated_at=generated_at,
                metrics={
                    "recommendation_request_count": 3,
                    "qdrant_failed_point_count": 0,
                },
            )

    monkeypatch.setattr(
        operations.OperationalMetricsService,
        "from_session",
        classmethod(lambda cls, session: _FakeService()),
    )

    def _override_db():
        yield object()

    app.dependency_overrides[get_db] = _override_db
    try:
        response = TestClient(app).get("/v1/operations/metrics")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "recommendation-service"
    assert payload["metrics"]["recommendation_request_count"] == 3
    assert payload["metrics"]["qdrant_failed_point_count"] == 0


def test_json_log_formatter_includes_structured_payload() -> None:
    record = logging.LogRecord(
        name="app.services.recommendations",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="recommendation request completed",
        args=(),
        exc_info=None,
    )
    record.structured = {
        "event": "recommendation.completed",
        "request_id": "req-1",
        "profile_revision": 2,
        "scoring_config": "scoring_v1",
        "vector_schema": "taste_v1",
    }

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["message"] == "recommendation request completed"
    assert payload["event"] == "recommendation.completed"
    assert payload["request_id"] == "req-1"
    assert payload["profile_revision"] == 2
    assert payload["scoring_config"] == "scoring_v1"
    assert payload["vector_schema"] == "taste_v1"


class _FakeOperationalMetricsRepository:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def recommendation_request_count(self) -> int:
        return 10

    def recommendation_result_count(self) -> int:
        return 30

    def empty_recommendation_request_count(self) -> int:
        return 2

    def profile_state_count(self) -> int:
        return 8

    def profile_state_count_by_status(self, status: str) -> int:
        return {
            "missing": 2,
            "stale": 1,
            "failed_generation": 1,
        }.get(status, 0)

    def active_beverage_count(self) -> int:
        return 60

    def qdrant_point_count_by_status(self, status: str) -> int:
        return {
            "pending": 1,
            "failed": 0,
        }.get(status, 0)

    def survey_sync_event_count_by_status(self, status: str) -> int:
        return {
            "pending": 1,
            "retry": 2,
            "dead_letter": 1,
        }.get(status, 0)

    def map_snapshot_sync_event_count_by_status(self, status: str) -> int:
        return {
            "pending": 3,
            "retry": 4,
            "dead_letter": 0,
        }.get(status, 0)

    def dead_letter_event_count(self) -> int:
        return 1

    def oldest_survey_cursor_synced_at(self) -> datetime:
        return self._now - timedelta(minutes=5)

    def oldest_map_snapshot_cursor_synced_at(self) -> datetime:
        return self._now - timedelta(minutes=15)


@dataclass(frozen=True)
class _FakeCatalogAuditReport:
    critical_count: int
    warning_count: int


class _FakeCatalogAudit:
    def __init__(self, *, critical_count: int, warning_count: int) -> None:
        self._report = _FakeCatalogAuditReport(
            critical_count=critical_count,
            warning_count=warning_count,
        )

    def audit_active_catalog(self) -> _FakeCatalogAuditReport:
        return self._report
