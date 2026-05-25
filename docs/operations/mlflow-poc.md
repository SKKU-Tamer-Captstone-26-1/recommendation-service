# MLflow Proof of Concept

## Purpose

This document defines the Plan 010 MLflow proof of concept.

The POC validates experiment artifacts only. It does not train or serve a
production ranker, and it does not replace deterministic `scoring_v1`.

## Inputs

Run the training dataset export first:

```bash
python3 -m app.tools.export_training_dataset \
  --from 2026-05-25T00:00:00Z \
  --to 2026-05-26T00:00:00Z \
  --output /private/tmp/recommendation-training-dataset
```

Then create MLflow-compatible local artifacts:

```bash
python3 -m app.tools.mlflow_poc \
  --dataset-export-dir /private/tmp/recommendation-training-dataset \
  --output /private/tmp/recommendation-mlflow-poc
```

## Output Files

```text
baseline_run.json
candidate_model_run.json
evaluation_report.json
model_registry_candidate.json
model_card.md
```

## Lifecycle Rule

The only allowed registry stage in this POC is:

```text
candidate
```

Production serving stays:

```text
deterministic_scoring_v1
```

## Future MLflow Deployment

When approved, the staging MLflow stack should use:

```text
MLflow Tracking Server
PostgreSQL backend store separate from recommendation-service schema
S3/GCS/MinIO artifact store
training job container
model registry
```

Do not mix the MLflow backend store with recommendation-service application
tables.

## Promotion Gates

Do not promote any model until all are true:

```text
offline metric pass
shadow comparison pass
canary guardrail pass
rollback plan exists
model version recorded in recommendation logs
```

## Acceptance Criteria

```text
mlflow_baseline_run = pass
candidate_model_run = pass
evaluation_report_artifact = pass
model_card_artifact = pass
model_registry_candidate_only = pass
production_ranker_unchanged = pass
```
