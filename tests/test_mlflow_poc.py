import json
from datetime import UTC, datetime

from app.services.mlflow_poc import (
    build_mlflow_poc_artifacts,
    write_mlflow_poc_artifacts,
)


def test_mlflow_poc_artifacts_keep_candidate_out_of_production(tmp_path) -> None:
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    _write_json(
        dataset_dir / "manifest.json",
        {
            "dataset_hash": "abc123",
            "record_count": 10,
            "feature_schema_version": "recommendation_training_features_v1",
        },
    )
    _write_json(
        dataset_dir / "feature_schema.json",
        {"version": "recommendation_training_features_v1"},
    )
    _write_json(
        dataset_dir / "data_quality_report.json",
        {
            "positive_label_records": 3,
            "negative_label_records": 1,
            "missing_model_features": 0,
        },
    )

    artifacts = build_mlflow_poc_artifacts(
        dataset_export_dir=dataset_dir,
        generated_at=datetime(2026, 5, 25, tzinfo=UTC),
    )
    output_dir = tmp_path / "mlflow"
    write_mlflow_poc_artifacts(artifacts, output_dir)

    assert artifacts.baseline_run["ranker"] == "deterministic_scoring_v1"
    assert artifacts.baseline_run["production_ranker_changed"] is False
    assert artifacts.candidate_run["run_type"] == "candidate"
    assert artifacts.candidate_run["promotion_allowed"] is False
    assert artifacts.model_registry["stage"] == "candidate"
    assert artifacts.model_registry["serving_enabled"] is False
    assert artifacts.evaluation_report["production_ranker_unchanged"] is True
    assert (output_dir / "baseline_run.json").exists()
    assert (output_dir / "candidate_model_run.json").exists()
    assert (output_dir / "evaluation_report.json").exists()
    assert (output_dir / "model_registry_candidate.json").exists()
    assert "Candidate only" in (output_dir / "model_card.md").read_text()


def _write_json(path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True) + "\n")
