# Training Dataset Export

## Purpose

This document defines the Plan 010 offline training dataset export for future ML
experiments.

The export is not a production model. It prepares recommendation-owned logs for
offline analysis and MLflow experiments while keeping deterministic `scoring_v1`
as the production ranker.

## Command

```bash
python3 -m app.tools.export_training_dataset \
  --from 2026-05-25T00:00:00Z \
  --to 2026-05-26T00:00:00Z \
  --output /private/tmp/recommendation-training-dataset
```

Current format:

```text
jsonl
```

Parquet can be added later after dependency and storage policy approval.

## Output Files

```text
dataset.jsonl
manifest.json
feature_schema.json
label_definitions.json
data_quality_report.json
```

## Allowed Sources

The export may read only recommendation-owned data:

- `recommendation_requests`
- `recommendation_results`
- `recommendation_explanations`
- `recommendation_interactions`
- `taste_profile_revisions`
- source snapshot metadata already stored in recommendation logs

The export must not read:

- survey-service database
- map-service database
- auth-service database
- raw survey answers

## Privacy and Boundary Notes

`external_user_id` is hashed before export.

The export includes derived profile metadata such as preferred categories,
budget range, experience level, mapper version, and vector schema version. It
does not include raw survey answers.

## Label Definitions

Initial labels:

```text
impression
click
save
dismiss
detail_view
positive = click + save + detail_view
negative = dismiss
```

These are weak product labels until enough real traffic exists.

`impression` is required for reliable rate metrics such as CTR:

```text
ctr = click / impression
```

Feedback event metadata is not a label. Client-generated feedback metadata is
restricted to:

```text
client_platform
app_version
surface
session_id_hash
list_position
visible_ms
source
```

The service rejects unsupported or PII-like metadata keys before storing
`recommendation_interactions`. Training exports must continue to derive labels
from recommendation-owned interaction rows only.

## Acceptance Criteria

```text
dataset_export_command = pass
feature_schema_version = pass
label_definition_doc = pass
dataset_manifest_hash = pass
no_raw_survey_export = pass
no_cross_service_db_access = pass
```
