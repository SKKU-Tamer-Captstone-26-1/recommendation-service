from unittest.mock import MagicMock

from app.core.config import Settings
from app.models.versioning import MapperVersion, ScoringConfig, VectorSchemaVersion
from app.repositories.versioning import VersioningRepository
from app.services.foundation import FoundationService


def test_foundation_service_reports_ready_when_active_versions_exist() -> None:
    repository = MagicMock(spec=VersioningRepository)
    repository.get_active_vector_schema.return_value = VectorSchemaVersion(
        name="taste",
        version="taste_v1",
        dimensions_json={},
        dimension_count=16,
    )
    repository.get_active_mapper_version.return_value = MapperVersion(
        name="survey_mapper",
        version="survey_mapper_v1",
        compatible_vector_schema="taste_v1",
        rules_json={},
    )
    repository.list_active_scoring_configs.return_value = (
        ScoringConfig(
            name="default_scoring",
            version="scoring_v1",
            target_type="beverage",
            category="all",
            weights_json={},
            reason_code_rules_json={},
        ),
        ScoringConfig(
            name="default_scoring",
            version="scoring_v1",
            target_type="venue",
            category="all",
            weights_json={},
            reason_code_rules_json={},
        ),
    )

    service = FoundationService(repository, Settings())
    state = service.load_active_registry_state()

    assert state.is_ready
    assert state.missing_keys == ()


def test_foundation_service_reports_missing_version_records() -> None:
    repository = MagicMock(spec=VersioningRepository)
    repository.get_active_vector_schema.return_value = None
    repository.get_active_mapper_version.return_value = None
    repository.list_active_scoring_configs.return_value = ()

    service = FoundationService(repository, Settings())
    state = service.load_active_registry_state()

    assert not state.is_ready
    assert state.missing_keys == (
        "vector_schema:taste_v1",
        "mapper:survey_mapper_v1",
        "scoring:scoring_v1:beverage",
        "scoring:scoring_v1:venue",
    )
