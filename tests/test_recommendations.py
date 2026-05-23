import uuid

from app.models.catalog import BeverageItem
from app.models.profile import TasteProfileRevision
from app.models.vector import RecommendationVector
from app.models.versioning import ScoringConfig
from app.repositories.catalog import BeverageVectorCandidate
from app.services.recommendations import score_beverage_candidate


def test_score_beverage_candidate_is_deterministic_and_explainable() -> None:
    beverage_id = uuid.uuid4()
    profile = TasteProfileRevision(
        external_user_id="usr_123",
        profile_revision=1,
        survey_response_id="surv_resp_123",
        survey_version="survey_v1",
        survey_response_revision=1,
        mapper_version_id=uuid.uuid4(),
        vector_schema_version_id=uuid.uuid4(),
        taste_vector=[
            0.8,
            0.1,
            0.0,
            0.7,
            0.0,
            0.5,
            0.0,
            0.2,
            0.0,
            0.5,
            0.0,
            0.0,
            0.3,
            0.0,
            0.0,
            0.0,
        ],
        taste_vector_json={
            "sweet": 0.8,
            "fruity": 0.1,
            "dried_fruit": 0.0,
            "woody": 0.7,
            "smoky": 0.0,
            "nutty": 0.5,
            "floral": 0.0,
            "spicy": 0.2,
            "herbal": 0.0,
            "body": 0.5,
            "acidity": 0.0,
            "carbonation": 0.0,
            "alcohol_intensity": 0.3,
            "bitterness": 0.0,
            "tannin": 0.0,
            "roasted": 0.0,
        },
        confidence_json={},
        preferred_categories=["whiskey"],
        preferred_keywords=["vanilla_caramel"],
        experience_level="beginner",
        status="active",
        generation_metadata_json={},
    )
    candidate = BeverageVectorCandidate(
        beverage=BeverageItem(
            id=beverage_id,
            category="whiskey",
            name_ko="테스트 버번",
            name_en="Test Bourbon",
            active=True,
            metadata_json={
                "catalog_key": "whiskey.test_bourbon",
                "style": "bourbon",
                "beginner_friendly_score": 0.8,
                "popularity_hint": "global_high",
                "reason_code_hints": ["MATCHES_VANILLA_CARAMEL"],
            },
        ),
        vector=RecommendationVector(
            owner_type="beverage_item",
            owner_id=beverage_id,
            vector_schema_version_id=profile.vector_schema_version_id,
            vector=[
                0.75,
                0.1,
                0.0,
                0.65,
                0.0,
                0.45,
                0.0,
                0.25,
                0.0,
                0.6,
                0.0,
                0.0,
                0.4,
                0.0,
                0.0,
                0.0,
            ],
            vector_json={
                "sweet": 0.75,
                "fruity": 0.1,
                "dried_fruit": 0.0,
                "woody": 0.65,
                "smoky": 0.0,
                "nutty": 0.45,
                "floral": 0.0,
                "spicy": 0.25,
                "herbal": 0.0,
                "body": 0.6,
                "acidity": 0.0,
                "carbonation": 0.0,
                "alcohol_intensity": 0.4,
                "bitterness": 0.0,
                "tannin": 0.0,
                "roasted": 0.0,
            },
            confidence_json={},
            source_hash="hash",
            source_metadata_json={},
        ),
        flavor_profile=None,
    )
    scoring = ScoringConfig(
        name="default_scoring",
        version="scoring_v1",
        target_type="beverage",
        category="all",
        weights_json={
            "taste_similarity_weighted": 0.65,
            "budget_fit": 0.10,
            "category_fit": 0.10,
            "experience_fit": 0.05,
            "popularity_or_quality": 0.05,
            "diversity_adjustment": 0.05,
        },
        reason_code_rules_json={},
        status="active",
    )

    first = score_beverage_candidate(
        profile=profile,
        candidate=candidate,
        scoring_config=scoring,
    )
    second = score_beverage_candidate(
        profile=profile,
        candidate=candidate,
        scoring_config=scoring,
    )

    assert first == second
    assert first.final_score > 0.8
    assert "MATCHES_VANILLA_CARAMEL" in first.reason_codes
    assert "CATEGORY_MATCH" in first.reason_codes
