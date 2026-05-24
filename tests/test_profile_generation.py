import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.models.enums import ProfileStatus
from app.models.profile import TasteProfileRevision, UserProfileState
from app.models.versioning import MapperVersion
from app.services.profile_generation import (
    ProfileGenerationService,
    SurveyMapperV1,
    SurveyProfileInput,
)


def test_survey_mapper_v1_generates_taste_v1_profile() -> None:
    survey_input = SurveyProfileInput(
        survey_response_id="surv_resp_123",
        external_user_id="usr_123",
        survey_version="survey_v1",
        response_revision=1,
        completed_at=datetime(2026, 5, 23, tzinfo=UTC),
        answers={
            "experience_level": "beginner",
            "categories": ["whiskey", "cocktail"],
            "category_traits": {"whiskey": ["smoky_peat"], "cocktail": ["sour"]},
            "global_keywords": ["vanilla_caramel", "nutty"],
            "budget_range": "30000_100000",
        },
    )

    generated = SurveyMapperV1().map(survey_input)

    assert len(generated.taste_vector) == 16
    assert generated.taste_vector_json["sweet"] >= 0.8
    assert generated.taste_vector_json["woody"] >= 0.5
    assert generated.taste_vector_json["smoky"] >= 0.8
    assert generated.preferred_categories == ["whiskey", "cocktail"]
    assert generated.preferred_keywords == ["vanilla_caramel", "nutty"]
    assert generated.budget_range == "30000_100000"
    assert generated.source_snapshot_hash


def test_profile_generation_is_idempotent_for_same_response_mapper() -> None:
    mapper_id = uuid.uuid4()
    profile = TasteProfileRevision(
        id=uuid.uuid4(),
        external_user_id="usr_123",
        profile_revision=1,
        survey_response_id="surv_resp_123",
        survey_version="survey_v1",
        survey_response_revision=1,
        mapper_version_id=mapper_id,
        vector_schema_version_id=uuid.uuid4(),
        taste_vector=[0.0] * 16,
        taste_vector_json={},
        confidence_json={},
        preferred_categories=[],
        preferred_keywords=[],
        status=ProfileStatus.ACTIVE.value,
        generation_metadata_json={"source_snapshot_hash": "hash_1"},
    )
    state = UserProfileState(
        external_user_id="usr_123",
        status=ProfileStatus.ACTIVE.value,
    )
    session = MagicMock(spec=Session)
    session.scalar.side_effect = [
        MapperVersion(
            id=mapper_id,
            name="survey_mapper",
            version="survey_mapper_v1",
            compatible_vector_schema="taste_v1",
            rules_json={},
            status="active",
        ),
        profile,
        object(),
    ]
    session.get.return_value = state

    result = ProfileGenerationService(session).generate_from_survey_input(
        SurveyProfileInput(
            survey_response_id="surv_resp_123",
            external_user_id="usr_123",
            survey_version="survey_v1",
            response_revision=1,
            completed_at=datetime(2026, 5, 23, tzinfo=UTC),
            answers={},
        ),
    )

    assert result is profile
    assert state.active_profile_revision_id == profile.id
    assert state.status == ProfileStatus.ACTIVE.value
    session.add.assert_not_called()
