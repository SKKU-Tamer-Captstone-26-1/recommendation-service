"""Create local MLflow-compatible POC artifacts without changing ranking."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.services.mlflow_poc import (
    build_mlflow_poc_artifacts,
    write_mlflow_poc_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-export-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    artifacts = build_mlflow_poc_artifacts(
        dataset_export_dir=Path(args.dataset_export_dir),
    )
    output_dir = Path(args.output)
    write_mlflow_poc_artifacts(artifacts, output_dir)
    print(
        "mlflow poc artifacts "
        f"baseline={artifacts.baseline_run['run_name']} "
        f"candidate={artifacts.candidate_run['run_name']} "
        f"stage={artifacts.model_registry['stage']} "
        f"production_ranker_unchanged="
        f"{artifacts.evaluation_report['production_ranker_unchanged']} "
        f"output={output_dir}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
