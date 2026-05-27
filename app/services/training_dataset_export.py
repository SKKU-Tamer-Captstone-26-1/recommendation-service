from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import InteractionEventType
from app.models.profile import TasteProfileRevision
from app.models.recommendation_event import (
    RecommendationExplanation,
    RecommendationInteraction,
    RecommendationRequest,
    RecommendationResult,
)

FEATURE_SCHEMA_VERSION = "recommendation_training_features_v1"
LABEL_SCHEMA_VERSION = "recommendation_interaction_labels_v1"
LABEL_EVENT_TYPES = tuple(event.value for event in InteractionEventType)


@dataclass(frozen=True)
class TrainingDatasetExport:
    generated_at: str
    format: str
    record_count: int
    dataset_hash: str
    records: tuple[dict[str, Any], ...]
    manifest: dict[str, Any]
    feature_schema: dict[str, Any]
    label_definitions: dict[str, Any]
    data_quality_report: dict[str, Any]


def export_training_dataset(
    session: Session,
    *,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    generated_at: datetime | None = None,
) -> TrainingDatasetExport:
    results = _load_result_rows(session, from_time=from_time, to_time=to_time)
    result_ids = [result.id for result, _request, _profile in results]
    explanations = _explanations_by_result_id(session, result_ids)
    interactions = _interactions_by_result_id(session, result_ids)
    records = tuple(
        _training_record(
            result=result,
            request=request,
            profile=profile,
            explanation=explanations.get(result.id),
            interactions=interactions.get(result.id, ()),
        )
        for result, request, profile in results
    )
    return build_training_dataset_export(
        records=records,
        from_time=from_time,
        to_time=to_time,
        generated_at=generated_at,
    )


def build_training_dataset_export(
    *,
    records: tuple[dict[str, Any], ...],
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    generated_at: datetime | None = None,
) -> TrainingDatasetExport:
    generated = _iso(generated_at or datetime.now(UTC))
    normalized_records = tuple(_normalize_json(record) for record in records)
    dataset_hash = _dataset_hash(normalized_records)
    feature_schema = _feature_schema()
    label_definitions = _label_definitions()
    data_quality_report = _quality_report(normalized_records)
    manifest = {
        "generated_at": generated,
        "format": "jsonl",
        "record_count": len(normalized_records),
        "dataset_hash": dataset_hash,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "label_schema_version": LABEL_SCHEMA_VERSION,
        "from_time": _iso(from_time),
        "to_time": _iso(to_time),
        "source_tables": [
            "recommendation_requests",
            "recommendation_results",
            "recommendation_explanations",
            "recommendation_interactions",
            "taste_profile_revisions",
        ],
        "source_boundary": (
            "recommendation-owned logs and derived profile metadata only; "
            "raw survey answers and external service storage are excluded"
        ),
    }
    return TrainingDatasetExport(
        generated_at=generated,
        format="jsonl",
        record_count=len(normalized_records),
        dataset_hash=dataset_hash,
        records=normalized_records,
        manifest=manifest,
        feature_schema=feature_schema,
        label_definitions=label_definitions,
        data_quality_report=data_quality_report,
    )


def write_training_dataset_export(
    export: TrainingDatasetExport,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_dir / "dataset.jsonl", export.records)
    _write_json(output_dir / "manifest.json", export.manifest)
    _write_json(output_dir / "feature_schema.json", export.feature_schema)
    _write_json(output_dir / "label_definitions.json", export.label_definitions)
    _write_json(output_dir / "data_quality_report.json", export.data_quality_report)


def _load_result_rows(
    session: Session,
    *,
    from_time: datetime | None,
    to_time: datetime | None,
) -> tuple[
    tuple[RecommendationResult, RecommendationRequest, TasteProfileRevision | None],
    ...,
]:
    statement = (
        select(RecommendationResult, RecommendationRequest, TasteProfileRevision)
        .join(
            RecommendationRequest,
            RecommendationResult.request_id == RecommendationRequest.id,
        )
        .outerjoin(
            TasteProfileRevision,
            RecommendationRequest.profile_revision_id == TasteProfileRevision.id,
        )
        .order_by(RecommendationRequest.created_at, RecommendationResult.rank)
    )
    if from_time is not None:
        statement = statement.where(RecommendationRequest.created_at >= from_time)
    if to_time is not None:
        statement = statement.where(RecommendationRequest.created_at < to_time)
    return tuple(session.execute(statement).all())


def _explanations_by_result_id(
    session: Session,
    result_ids: list[Any],
) -> dict[Any, RecommendationExplanation]:
    if not result_ids:
        return {}
    rows = session.scalars(
        select(RecommendationExplanation).where(
            RecommendationExplanation.result_id.in_(result_ids),
        ),
    ).all()
    return {row.result_id: row for row in rows}


def _interactions_by_result_id(
    session: Session,
    result_ids: list[Any],
) -> dict[Any, tuple[RecommendationInteraction, ...]]:
    if not result_ids:
        return {}
    rows = session.scalars(
        select(RecommendationInteraction)
        .where(RecommendationInteraction.result_id.in_(result_ids))
        .order_by(RecommendationInteraction.created_at, RecommendationInteraction.id),
    ).all()
    grouped: dict[Any, list[RecommendationInteraction]] = {}
    for row in rows:
        grouped.setdefault(row.result_id, []).append(row)
    return {key: tuple(value) for key, value in grouped.items()}


def _training_record(
    *,
    result: RecommendationResult,
    request: RecommendationRequest,
    profile: TasteProfileRevision | None,
    explanation: RecommendationExplanation | None,
    interactions: tuple[RecommendationInteraction, ...],
) -> dict[str, Any]:
    labels = _interaction_labels(interactions)
    return {
        "identity": {
            "request_id": str(request.id),
            "result_id": str(result.id),
            "external_user_hash": _hash_user_id(request.external_user_id),
            "target_type": result.target_type,
            "target_id": result.target_id,
            "rank": result.rank,
            "created_at": _iso(request.created_at),
        },
        "request": {
            "target_type": request.target_type,
            "filters": request.filters_json,
            "context": request.request_context_json,
            "profile_revision_id": str(request.profile_revision_id)
            if request.profile_revision_id
            else None,
            "scoring_config_id": str(request.scoring_config_id)
            if request.scoring_config_id
            else None,
        },
        "profile": _profile_features(profile),
        "features": {
            "similarity_score": result.similarity_score,
            "final_score": result.final_score,
            "score_breakdown": result.score_breakdown_json,
            "model_features": result.source_snapshot_json.get("model_features"),
            "source_snapshot": result.source_snapshot_json,
            "qdrant_point_id": result.qdrant_point_id,
        },
        "explanation": {
            "reason_codes": explanation.reason_codes if explanation else [],
            "matched_dimensions": explanation.matched_dimensions_json
            if explanation
            else {},
            "template_version": explanation.template_version if explanation else None,
        },
        "labels": labels,
    }


def _profile_features(profile: TasteProfileRevision | None) -> dict[str, Any]:
    if profile is None:
        return {}
    return {
        "profile_revision": profile.profile_revision,
        "mapper_version_id": str(profile.mapper_version_id),
        "vector_schema_version_id": str(profile.vector_schema_version_id),
        "scoring_config_id": str(profile.scoring_config_id)
        if profile.scoring_config_id
        else None,
        "preferred_categories": profile.preferred_categories,
        "preferred_keywords": profile.preferred_keywords,
        "budget_range": profile.budget_range,
        "experience_level": profile.experience_level,
        "status": profile.status,
        "generated_at": _iso(profile.generated_at),
    }


def _interaction_labels(
    interactions: tuple[RecommendationInteraction, ...],
) -> dict[str, Any]:
    counts = {event_type: 0 for event_type in LABEL_EVENT_TYPES}
    for interaction in interactions:
        if interaction.event_type in counts:
            counts[interaction.event_type] += 1
    return {
        **counts,
        "positive": counts["click"] + counts["save"] + counts["detail_view"],
        "negative": counts["dismiss"],
        "interaction_count": sum(counts.values()),
    }


def _feature_schema() -> dict[str, Any]:
    return {
        "version": FEATURE_SCHEMA_VERSION,
        "format": "jsonl",
        "primary_key": "identity.result_id",
        "features": {
            "profile": [
                "profile_revision",
                "mapper_version_id",
                "vector_schema_version_id",
                "preferred_categories",
                "preferred_keywords",
                "budget_range",
                "experience_level",
            ],
            "result": [
                "similarity_score",
                "final_score",
                "score_breakdown",
                "model_features",
                "source_snapshot",
                "reason_codes",
                "matched_dimensions",
            ],
        },
        "excluded_sources": [
            "raw survey answers",
            "survey-service raw storage",
            "map-service canonical storage",
            "auth-service identity storage",
        ],
    }


def _label_definitions() -> dict[str, Any]:
    return {
        "version": LABEL_SCHEMA_VERSION,
        "labels": {
            "impression": "recommendation card was shown",
            "click": "user clicked the recommendation",
            "save": "user saved the recommendation",
            "dismiss": "user dismissed the recommendation",
            "detail_view": "user opened recommendation detail",
            "positive": "click + save + detail_view",
            "negative": "dismiss",
        },
    }


def _quality_report(records: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    target_counts: dict[str, int] = {}
    missing_model_features = 0
    positive_count = 0
    negative_count = 0
    for record in records:
        target_type = str(record["identity"]["target_type"])
        target_counts[target_type] = target_counts.get(target_type, 0) + 1
        if record["features"].get("model_features") is None:
            missing_model_features += 1
        labels = record["labels"]
        positive_count += int(labels["positive"] > 0)
        negative_count += int(labels["negative"] > 0)
    return {
        "record_count": len(records),
        "target_type_counts": target_counts,
        "missing_model_features": missing_model_features,
        "positive_label_records": positive_count,
        "negative_label_records": negative_count,
    }


def _dataset_hash(records: tuple[dict[str, Any], ...]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(_json_line(record).encode("utf-8"))
    return digest.hexdigest()


def _hash_user_id(external_user_id: str) -> str:
    return hashlib.sha256(external_user_id.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _write_jsonl(path: Path, records: tuple[dict[str, Any], ...]) -> None:
    path.write_text(
        "".join(_json_line(record) + "\n" for record in records),
    )


def _json_line(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_json(item) for key, item in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [_normalize_json(item) for item in value]
    if isinstance(value, datetime):
        return _iso(value)
    return value


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
