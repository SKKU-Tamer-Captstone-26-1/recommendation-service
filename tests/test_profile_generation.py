from datetime import UTC, datetime

from app.services.profile_generation import SurveyMapperV1, SurveyProfileInput


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
