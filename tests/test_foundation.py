from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.base import Base
from app.domain.foundation_versions import (
    SCORING_V1,
    SURVEY_MAPPER_V1,
    scoring_v1_payloads,
    survey_mapper_v1_payload,
    taste_v1_vector_schema_payload,
)
from app.domain.vector_schema import TASTE_V1_DIMENSION_COUNT, TASTE_V1_DIMENSIONS
from app.grpc.server import create_grpc_server
from app.main import app


def test_live_health_endpoint_is_dependency_free() -> None:
    client = TestClient(app)

    response = client.get("/health/live")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["dependencies"] == []


def test_service_status_exposes_active_foundation_versions() -> None:
    client = TestClient(app)

    response = client.get("/v1/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "recommendation-service"
    assert payload["active_vector_schema"] == "taste_v1"
    assert payload["active_survey_mapper"] == "survey_mapper_v1"
    assert payload["active_scoring_config"] == "scoring_v1"


def test_model_metadata_registers_foundation_tables() -> None:
    required_tables = {
        "user_profile_state",
        "taste_profile_revisions",
        "survey_source_snapshots",
        "vector_schema_versions",
        "mapper_versions",
        "recommendation_vectors",
        "qdrant_points",
        "venue_snapshots",
        "venue_menu_snapshots",
        "venue_inventory_snapshots",
        "venue_price_snapshots",
        "survey_sync_events",
        "dead_letter_events",
        "recommendation_staging.beverage_collection_runs",
        "recommendation_staging.beverage_catalog_candidates",
        "recommendation_staging.beverage_flavor_profile_candidates",
        "recommendation_staging.beverage_knowledge_candidates",
        "recommendation_staging.beverage_price_observation_candidates",
        "recommendation_staging.beverage_source_refs",
    }

    assert required_tables.issubset(Base.metadata.tables)
    assert "venues" not in Base.metadata.tables
    assert "venue_menu_items" not in Base.metadata.tables


def test_taste_v1_dimension_order_is_stable() -> None:
    dimension_names = [dimension.name for dimension in TASTE_V1_DIMENSIONS]

    assert TASTE_V1_DIMENSION_COUNT == 16
    assert dimension_names[0] == "sweet"
    assert dimension_names[15] == "roasted"


def test_foundation_version_payloads_match_active_settings() -> None:
    vector_payload = taste_v1_vector_schema_payload()
    mapper_payload = survey_mapper_v1_payload()
    scoring_payloads = scoring_v1_payloads()

    assert vector_payload["version"] == "taste_v1"
    assert vector_payload["dimension_count"] == 16
    assert vector_payload["status"] == "active"
    assert mapper_payload["version"] == SURVEY_MAPPER_V1
    assert mapper_payload["compatible_vector_schema"] == "taste_v1"
    assert {payload["target_type"] for payload in scoring_payloads} == {
        "beverage",
        "venue",
    }
    assert all(payload["version"] == SCORING_V1 for payload in scoring_payloads)
    assert all(payload["status"] == "active" for payload in scoring_payloads)


def test_grpc_health_server_can_be_created() -> None:
    settings = Settings(grpc_host="127.0.0.1", grpc_port=50051)
    server = create_grpc_server(settings, bind_port=False)

    assert server is not None
