import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.grpc.gen import recommendation_pb2
from app.grpc.recommendation_service import _event_type_from_proto
from app.models.catalog import BeverageItem
from app.models.profile import TasteProfileRevision
from app.models.recommendation_event import RecommendationInteraction
from app.models.vector import RecommendationVector
from app.models.versioning import ScoringConfig
from app.repositories.catalog import BeverageVectorCandidate
from app.services.recommendations import (
    BeverageRecommendationService,
    beverage_model_features,
    score_beverage_candidate,
    validate_interaction_metadata,
)


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

    features = beverage_model_features(
        profile=profile,
        candidate=candidate,
        score=first,
        scoring_config=scoring,
    )

    assert features["taste_similarity"] == first.similarity
    assert features["score_breakdown"] == first.breakdown
    assert features["candidate_catalog_key"] == "whiskey.test_bourbon"
    assert features["scoring_config_version"] == "scoring_v1"


def test_record_interaction_accepts_impression_with_allowed_metadata() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = None
    request_id = uuid.uuid4()
    result_id = uuid.uuid4()

    BeverageRecommendationService(session).record_interaction(
        request_id=request_id,
        result_id=result_id,
        event_type="impression",
        idempotency_key=" impression-1 ",
        metadata={
            "client_platform": "flutter",
            "app_version": "1.0.0",
            "surface": "home_recommendation_card",
            "session_id_hash": "sha256:abc",
            "list_position": 1.0,
            "visible_ms": 2300,
            "source": "client",
        },
    )

    interaction = session.add.call_args.args[0]
    assert isinstance(interaction, RecommendationInteraction)
    assert interaction.request_id == request_id
    assert interaction.result_id == result_id
    assert interaction.event_type == "impression"
    assert interaction.idempotency_key == "impression-1"
    assert interaction.metadata_json == {
        "client_platform": "flutter",
        "app_version": "1.0.0",
        "surface": "home_recommendation_card",
        "session_id_hash": "sha256:abc",
        "list_position": 1,
        "visible_ms": 2300,
        "source": "client",
    }
    session.flush.assert_called_once()


def test_record_interaction_returns_duplicate_for_idempotency_key() -> None:
    existing_id = uuid.uuid4()
    existing = RecommendationInteraction(
        request_id=uuid.uuid4(),
        result_id=uuid.uuid4(),
        event_type="click",
        idempotency_key="event-1",
        metadata_json={},
    )
    existing.id = existing_id
    session = MagicMock(spec=Session)
    session.scalar.return_value = existing

    result = BeverageRecommendationService(session).record_interaction(
        request_id=uuid.uuid4(),
        result_id=uuid.uuid4(),
        event_type="click",
        idempotency_key="event-1",
        metadata={"source": "client"},
    )

    assert result.interaction_id == existing_id
    assert result.duplicate is True
    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_record_interaction_rejects_unsupported_event_type() -> None:
    session = MagicMock(spec=Session)

    with pytest.raises(ValueError, match="unsupported recommendation event type"):
        BeverageRecommendationService(session).record_interaction(
            request_id=uuid.uuid4(),
            result_id=uuid.uuid4(),
            event_type="share",
            idempotency_key="event-1",
            metadata={"source": "client"},
        )

    session.add.assert_not_called()


def test_interaction_metadata_rejects_unsupported_and_pii_like_keys() -> None:
    assert validate_interaction_metadata(
        {
            "client_platform": "flutter",
            "list_position": 2.0,
            "visible_ms": 100,
        },
    ) == {
        "client_platform": "flutter",
        "list_position": 2,
        "visible_ms": 100,
    }

    with pytest.raises(ValueError, match="unsupported recommendation event metadata"):
        validate_interaction_metadata({"load_profile": "beta"})

    with pytest.raises(ValueError, match="unsafe recommendation event metadata"):
        validate_interaction_metadata({"email": "user@example.com"})


def test_grpc_event_type_mapping_accepts_proto_impression() -> None:
    assert (
        _event_type_from_proto(
            recommendation_pb2.RECOMMENDATION_EVENT_TYPE_IMPRESSION,
        )
        == "impression"
    )
