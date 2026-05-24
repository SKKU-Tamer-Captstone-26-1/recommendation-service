"""Smoke operational metrics from recommendation-owned PostgreSQL state."""

from __future__ import annotations

from app.db.session import SessionLocal
from app.services.operational_metrics import OperationalMetricsService

REQUIRED_METRICS = {
    "recommendation_request_count",
    "recommendation_empty_rate",
    "profile_missing_rate",
    "survey_sync_max_lag_seconds",
    "map_snapshot_sync_max_lag_seconds",
    "catalog_audit_critical_count",
    "qdrant_failed_point_count",
}


def main() -> int:
    with SessionLocal() as session:
        snapshot = OperationalMetricsService.from_session(session).snapshot()

    missing = sorted(REQUIRED_METRICS - set(snapshot.metrics))
    if missing:
        raise RuntimeError(f"operational metrics missing keys: {', '.join(missing)}")
    if snapshot.metrics["catalog_audit_critical_count"] not in (0, None):
        raise RuntimeError(
            "catalog audit has critical failures: "
            f"{snapshot.metrics['catalog_audit_critical_count']}",
        )
    print(
        "operational metrics smoke "
        f"request_count={snapshot.metrics['recommendation_request_count']} "
        f"empty_rate={snapshot.metrics['recommendation_empty_rate']} "
        f"profile_missing_rate={snapshot.metrics['profile_missing_rate']} "
        f"catalog_critical={snapshot.metrics['catalog_audit_critical_count']} "
        f"qdrant_failed={snapshot.metrics['qdrant_failed_point_count']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
