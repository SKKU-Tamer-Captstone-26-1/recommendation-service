import uuid
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.models.profile import TasteProfileRevision, UserProfileState
from app.models.vector import QdrantPoint, RecommendationVector
from app.models.versioning import MapperVersion, ScoringConfig, VectorSchemaVersion
from app.repositories.profiles import ProfileRepository
from app.repositories.vectors import VectorRepository
from app.repositories.versioning import VersioningRepository


def test_versioning_repository_reads_active_version_records() -> None:
    session = MagicMock(spec=Session)
    vector_schema = VectorSchemaVersion(
        name="taste",
        version="taste_v1",
        dimensions_json={},
        dimension_count=16,
    )
    mapper = MapperVersion(
        name="survey_mapper",
        version="survey_mapper_v1",
        compatible_vector_schema="taste_v1",
        rules_json={},
    )
    scoring = ScoringConfig(
        name="default_scoring",
        version="scoring_v1",
        target_type="beverage",
        category="all",
        weights_json={},
        reason_code_rules_json={},
    )
    session.scalar.side_effect = [vector_schema, mapper, scoring]

    repository = VersioningRepository(session)

    assert repository.get_active_vector_schema("taste_v1") is vector_schema
    assert repository.get_active_mapper_version("survey_mapper_v1") is mapper
    assert (
        repository.get_active_scoring_config(
            version="scoring_v1",
            target_type="beverage",
        )
        is scoring
    )


def test_profile_repository_reads_profile_state_and_revisions() -> None:
    session = MagicMock(spec=Session)
    external_user_id = "usr_123"
    profile_revision_id = uuid.uuid4()
    profile_state = UserProfileState(external_user_id=external_user_id)
    profile_revision = TasteProfileRevision(
        id=profile_revision_id,
        external_user_id=external_user_id,
        profile_revision=1,
        survey_response_id="surv_resp_123",
        survey_version="survey_v1",
        survey_response_revision=1,
        mapper_version_id=uuid.uuid4(),
        vector_schema_version_id=uuid.uuid4(),
        taste_vector=[0.0] * 16,
        taste_vector_json={},
        preferred_categories=[],
        preferred_keywords=[],
    )
    session.scalar.side_effect = [
        profile_state,
        profile_revision,
        profile_revision,
    ]

    repository = ProfileRepository(session)

    assert repository.get_profile_state(external_user_id) is profile_state
    assert repository.get_profile_revision(profile_revision_id) is profile_revision
    assert repository.get_active_profile_revision(external_user_id) is profile_revision


def test_vector_repository_reads_vectors_and_qdrant_points() -> None:
    session = MagicMock(spec=Session)
    owner_id = uuid.uuid4()
    schema_id = uuid.uuid4()
    vector = RecommendationVector(
        owner_type="profile_revision",
        owner_id=owner_id,
        vector_schema_version_id=schema_id,
        vector=[0.0] * 16,
        vector_json={},
        source_hash="hash",
    )
    point = QdrantPoint(
        vector_id=uuid.uuid4(),
        collection_name="beverage_vectors_v1",
        point_id="point_123",
        payload_hash="payload_hash",
    )
    session.scalar.return_value = vector
    session.scalars.return_value.all.return_value = [point]

    repository = VectorRepository(session)

    assert (
        repository.get_vector_by_owner(
            owner_type="profile_revision",
            owner_id=owner_id,
            vector_schema_version_id=schema_id,
        )
        is vector
    )
    assert repository.list_qdrant_points(point.vector_id) == (point,)
