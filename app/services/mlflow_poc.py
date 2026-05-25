from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MlflowPocArtifacts:
    generated_at: str
    baseline_run: dict[str, Any]
    candidate_run: dict[str, Any]
    evaluation_report: dict[str, Any]
    model_registry: dict[str, Any]
    model_card: str


def build_mlflow_poc_artifacts(
    *,
    dataset_export_dir: Path,
    generated_at: datetime | None = None,
) -> MlflowPocArtifacts:
    generated = _iso(generated_at or datetime.now(UTC))
    manifest = _read_json(dataset_export_dir / "manifest.json")
    feature_schema = _read_json(dataset_export_dir / "feature_schema.json")
    quality_report = _read_json(dataset_export_dir / "data_quality_report.json")
    dataset_hash = str(manifest["dataset_hash"])
    record_count = int(manifest["record_count"])

    baseline_run = {
        "run_name": "deterministic_scoring_v1_baseline",
        "run_type": "baseline",
        "generated_at": generated,
        "ranker": "deterministic_scoring_v1",
        "production_ranker_changed": False,
        "dataset_hash": dataset_hash,
        "feature_schema_version": feature_schema["version"],
        "params": {
            "active_scoring_config": "scoring_v1",
            "model_family": "deterministic_rules",
            "serving_mode": "production_baseline",
        },
        "metrics": _baseline_metrics(quality_report, record_count),
    }
    candidate_run = {
        "run_name": "linear_candidate_shadow_only",
        "run_type": "candidate",
        "generated_at": generated,
        "dataset_hash": dataset_hash,
        "feature_schema_version": feature_schema["version"],
        "params": {
            "model_family": "linear_model_placeholder",
            "training_mode": "offline_poc",
            "serving_mode": "shadow_only",
        },
        "metrics": _candidate_placeholder_metrics(quality_report, record_count),
        "promotion_allowed": False,
        "promotion_blocker": "requires real labels, shadow evaluation, and canary",
    }
    evaluation_report = {
        "generated_at": generated,
        "dataset_hash": dataset_hash,
        "record_count": record_count,
        "baseline_run": baseline_run["run_name"],
        "candidate_run": candidate_run["run_name"],
        "production_ranker_unchanged": True,
        "candidate_stage": "candidate",
        "quality_report": quality_report,
        "decision": (
            "Do not promote. This POC validates ML experiment artifacts only."
        ),
    }
    model_registry = {
        "model_name": "recommendation_ranker",
        "registered_version": "candidate-local-poc",
        "stage": "candidate",
        "production_alias": None,
        "production_ranker": "deterministic_scoring_v1",
        "serving_enabled": False,
    }
    model_card = _model_card(
        generated_at=generated,
        dataset_hash=dataset_hash,
        record_count=record_count,
    )
    return MlflowPocArtifacts(
        generated_at=generated,
        baseline_run=baseline_run,
        candidate_run=candidate_run,
        evaluation_report=evaluation_report,
        model_registry=model_registry,
        model_card=model_card,
    )


def write_mlflow_poc_artifacts(
    artifacts: MlflowPocArtifacts,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "baseline_run.json", artifacts.baseline_run)
    _write_json(output_dir / "candidate_model_run.json", artifacts.candidate_run)
    _write_json(output_dir / "evaluation_report.json", artifacts.evaluation_report)
    _write_json(output_dir / "model_registry_candidate.json", artifacts.model_registry)
    (output_dir / "model_card.md").write_text(artifacts.model_card)


def _baseline_metrics(
    quality_report: dict[str, Any],
    record_count: int,
) -> dict[str, float | int]:
    return {
        "record_count": record_count,
        "positive_label_records": int(quality_report.get("positive_label_records", 0)),
        "negative_label_records": int(quality_report.get("negative_label_records", 0)),
        "missing_model_features": int(quality_report.get("missing_model_features", 0)),
    }


def _candidate_placeholder_metrics(
    quality_report: dict[str, Any],
    record_count: int,
) -> dict[str, float | int]:
    positive = int(quality_report.get("positive_label_records", 0))
    negative = int(quality_report.get("negative_label_records", 0))
    labeled = positive + negative
    label_coverage = round(labeled / record_count, 6) if record_count else 0.0
    return {
        "record_count": record_count,
        "label_coverage": label_coverage,
        "offline_ndcg_at_5": 0.0,
        "offline_map_at_5": 0.0,
    }


def _model_card(
    *,
    generated_at: str,
    dataset_hash: str,
    record_count: int,
) -> str:
    return f"""# Recommendation Ranker Candidate POC

## Status

Candidate only. Not approved for production serving.

## Generated

```text
generated_at: {generated_at}
dataset_hash: {dataset_hash}
record_count: {record_count}
production_ranker: deterministic_scoring_v1
```

## Intended Use

Validate MLflow experiment tracking artifacts and dataset wiring.

## Not Intended For

- production ranking
- autonomous model promotion
- replacing deterministic reason-code scoring

## Promotion Requirements

```text
offline metric pass
shadow comparison pass
canary guardrail pass
rollback plan exists
model version recorded in recommendation logs
```
"""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required MLflow POC input is missing: {path}")
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
