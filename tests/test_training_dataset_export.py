from datetime import UTC, datetime

from app.services.training_dataset_export import (
    FEATURE_SCHEMA_VERSION,
    build_training_dataset_export,
    write_training_dataset_export,
)


def test_training_dataset_export_builds_manifest_and_hash(tmp_path) -> None:
    records = (
        {
            "identity": {
                "request_id": "req-1",
                "result_id": "res-1",
                "external_user_hash": "hashed-user",
                "target_type": "beverage",
                "target_id": "bev-1",
                "rank": 1,
                "created_at": "2026-05-25T00:00:00+00:00",
            },
            "request": {
                "target_type": "beverage",
                "filters": {"category": "whiskey"},
                "context": {"pipeline": "postgres_beverage_v1"},
                "profile_revision_id": "profile-1",
                "scoring_config_id": "scoring-1",
            },
            "profile": {
                "profile_revision": 1,
                "mapper_version_id": "mapper-1",
                "vector_schema_version_id": "schema-1",
                "preferred_categories": ["whiskey"],
                "preferred_keywords": ["oak_woody"],
                "budget_range": "under_70000",
                "experience_level": "beginner",
            },
            "features": {
                "similarity_score": 0.9,
                "final_score": 0.8,
                "score_breakdown": {"taste_similarity_weighted": 0.6},
                "model_features": {"category_fit": 1.0},
                "source_snapshot": {"candidate_source": "postgres_catalog"},
                "qdrant_point_id": None,
            },
            "explanation": {
                "reason_codes": ["MATCHES_RICH_OAK_PROFILE"],
                "matched_dimensions": {"woody": 0.9},
                "template_version": "reason_template_v1",
            },
            "labels": {
                "impression": 1,
                "click": 1,
                "save": 0,
                "dismiss": 0,
                "detail_view": 0,
                "positive": 1,
                "negative": 0,
                "interaction_count": 2,
            },
        },
    )

    export = build_training_dataset_export(
        records=records,
        from_time=datetime(2026, 5, 25, tzinfo=UTC),
        to_time=datetime(2026, 5, 26, tzinfo=UTC),
        generated_at=datetime(2026, 5, 26, tzinfo=UTC),
    )
    write_training_dataset_export(export, tmp_path)

    assert export.record_count == 1
    assert len(export.dataset_hash) == 64
    assert export.manifest["feature_schema_version"] == FEATURE_SCHEMA_VERSION
    assert "raw survey answers" in export.feature_schema["excluded_sources"]
    assert export.data_quality_report["missing_model_features"] == 0
    assert (tmp_path / "dataset.jsonl").read_text().count("\n") == 1
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "feature_schema.json").exists()
    assert (tmp_path / "label_definitions.json").exists()
    assert (tmp_path / "data_quality_report.json").exists()


def test_training_dataset_hash_is_deterministic() -> None:
    records = (
        {
            "identity": {"result_id": "res-1", "target_type": "beverage"},
            "features": {"model_features": None},
            "labels": {"positive": 0, "negative": 0},
        },
    )

    first = build_training_dataset_export(records=records)
    second = build_training_dataset_export(records=records)

    assert first.dataset_hash == second.dataset_hash
    assert first.data_quality_report["missing_model_features"] == 1
