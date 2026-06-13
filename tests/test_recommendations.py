import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.domain.foundation_versions import scoring_v3_payloads
from app.domain.vector_schema import TASTE_V1_DIMENSIONS
from app.grpc.gen import recommendation_pb2
from app.grpc.recommendation_service import _event_type_from_proto
from app.models.catalog import BeverageItem
from app.models.profile import TasteProfileRevision
from app.models.recommendation_event import (
    RecommendationExplanation,
    RecommendationInteraction,
    RecommendationRequest,
    RecommendationResult,
)
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
    assert "현재 취향 프로필" in first.explanation
    assert "바닐라와 캐러멜" in first.explanation

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


def test_score_beverage_candidate_uses_catalog_price_budget_fit() -> None:
    profile = _beverage_profile()
    profile.budget_range = "under_30000"
    scoring = _beverage_scoring()
    in_budget = _beverage_candidate(
        name="Fixture Affordable Bourbon",
        style="bourbon",
        vector_value=1.0,
        price_min_krw=25000,
        price_max_krw=29000,
        price_observation_count=2,
    )
    expensive = _beverage_candidate(
        name="Fixture Premium Bourbon",
        style="bourbon",
        vector_value=1.0,
        price_min_krw=180000,
        price_max_krw=220000,
        price_observation_count=2,
    )

    affordable_score = score_beverage_candidate(
        profile=profile,
        candidate=in_budget,
        scoring_config=scoring,
    )
    premium_score = score_beverage_candidate(
        profile=profile,
        candidate=expensive,
        scoring_config=scoring,
    )
    features = beverage_model_features(
        profile=profile,
        candidate=in_budget,
        score=affordable_score,
        scoring_config=scoring,
    )

    assert affordable_score.final_score > premium_score.final_score
    assert affordable_score.breakdown["budget_fit"] > premium_score.breakdown[
        "budget_fit"
    ]
    assert "WITHIN_BUDGET" in affordable_score.reason_codes
    assert features["budget_feature"] == {
        "strategy": "catalog_price_range_soft_v1",
        "fit": features["budget_fit"],
        "confidence": 0.65,
        "evidence": "catalog_price_range",
        "budget_range": "under_30000",
        "budget_floor_krw": None,
        "budget_ceiling_krw": 30000,
        "price_min_krw": 25000,
        "price_max_krw": 29000,
        "price_mid_krw": 27000.0,
        "price_policy": "verified_krw_observations_not_live_truth",
    }
    assert features["budget_tradeoff"] == {
        "policy_version": "beverage_budget_tradeoff_v1",
        "status": "within_budget",
        "display_label_ko": "예산 적합",
        "note_ko": "검증된 카탈로그 가격대 기준으로 선택한 예산과 잘 맞습니다.",
        "budget_range": "under_30000",
        "budget_floor_krw": None,
        "budget_ceiling_krw": 30000,
        "price_min_krw": 25000,
        "price_max_krw": 29000,
        "price_mid_krw": 27000.0,
        "fit": features["budget_fit"],
        "confidence": 0.65,
        "evidence": "catalog_price_range",
        "price_policy": "verified_krw_observations_not_live_truth",
        "source": "catalog_price_not_live_offer",
    }

    premium_features = beverage_model_features(
        profile=profile,
        candidate=expensive,
        score=premium_score,
        scoring_config=scoring,
    )
    assert premium_features["budget_tradeoff"]["status"] == (
        "above_budget_soft_tradeoff"
    )
    assert "소프트 추천" in premium_features["budget_tradeoff"]["note_ko"]


def test_score_beverage_candidate_uses_category_weighted_similarity_v3() -> None:
    profile = _beverage_profile()
    profile.taste_vector = [1.0, 0.0, 0.0, 0.0, 1.0, *([0.0] * 11)]
    profile.taste_vector_json = {"sweet": 1.0, "smoky": 1.0}
    sweet_match = _beverage_candidate(
        name="Fixture Sweet Whiskey",
        style="bourbon",
        vector_value=1.0,
    )
    smoky_match = _beverage_candidate(
        name="Fixture Smoky Whiskey",
        style="peated single malt",
        vector_value=0.0,
    )
    smoky_match.vector.vector = [0.0, 0.0, 0.0, 0.0, 1.0, *([0.0] * 11)]
    smoky_match.vector.vector_json = {"smoky": 1.0}
    scoring = _beverage_scoring_v3()

    sweet_score = score_beverage_candidate(
        profile=profile,
        candidate=sweet_match,
        scoring_config=scoring,
    )
    smoky_score = score_beverage_candidate(
        profile=profile,
        candidate=smoky_match,
        scoring_config=scoring,
    )
    features = beverage_model_features(
        profile=profile,
        candidate=smoky_match,
        score=smoky_score,
        scoring_config=scoring,
    )

    assert smoky_score.similarity > sweet_score.similarity
    assert smoky_score.final_score > sweet_score.final_score
    assert features["taste_similarity_feature"]["strategy"] == (
        "category_weighted_similarity_v1"
    )
    assert features["taste_similarity_feature"]["dimension_weights"]["smoky"] == 1.35


def test_score_beverage_candidate_keeps_missing_price_budget_neutral() -> None:
    profile = _beverage_profile()
    profile.budget_range = "30000_50000"
    candidate = _beverage_candidate(
        name="Fixture Unpriced Whiskey",
        style="single malt scotch whisky",
        vector_value=1.0,
    )
    scoring = _beverage_scoring()

    score = score_beverage_candidate(
        profile=profile,
        candidate=candidate,
        scoring_config=scoring,
    )
    features = beverage_model_features(
        profile=profile,
        candidate=candidate,
        score=score,
        scoring_config=scoring,
    )

    assert features["budget_fit"] == 0.5
    assert features["budget_feature"]["evidence"] == "missing_price_or_budget"
    assert features["budget_feature"]["confidence"] == 0.0


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


def test_beverage_recommendations_exclude_beverage_ids() -> None:
    excluded = _beverage_candidate(
        name="Fixture Bourbon",
        style="bourbon",
        vector_value=1.0,
    )
    fallback = _beverage_candidate(
        name="Fixture Scotch",
        style="single malt scotch whisky",
        vector_value=0.92,
    )
    service, added = _beverage_service_with_candidates((excluded, fallback))

    response = service.get_beverage_recommendations(
        external_user_id="usr_123",
        exclude_beverage_ids=[str(excluded.beverage.id)],
        limit=2,
    )

    assert [item.target_id for item in response.results] == [
        str(fallback.beverage.id),
    ]
    request = _first_added(added, RecommendationRequest)
    assert request.filters_json["exclude_beverage_ids"] == [str(excluded.beverage.id)]
    assert request.filters_json["diversity_mode"] == "standard"
    assert request.request_context_json["excluded_beverage_count"] == 1


def test_beverage_recommendations_exclude_result_ids() -> None:
    excluded_result_id = uuid.uuid4()
    excluded = _beverage_candidate(
        name="Fixture Bourbon",
        style="bourbon",
        vector_value=1.0,
    )
    fallback = _beverage_candidate(
        name="Fixture Irish",
        style="Irish whiskey",
        vector_value=0.9,
    )
    service, added = _beverage_service_with_candidates(
        (excluded, fallback),
        result_rows=[(str(excluded.beverage.id),)],
    )

    response = service.get_beverage_recommendations(
        external_user_id="usr_123",
        exclude_result_ids=[str(excluded_result_id)],
        limit=2,
    )

    assert [item.target_id for item in response.results] == [
        str(fallback.beverage.id),
    ]
    request = _first_added(added, RecommendationRequest)
    assert request.filters_json["exclude_result_ids"] == [str(excluded_result_id)]
    assert request.request_context_json["excluded_result_count"] == 1


def test_beverage_recommendations_different_mode_avoids_excluded_style() -> None:
    excluded = _beverage_candidate(
        name="Fixture Bourbon",
        style="bourbon",
        vector_value=1.0,
    )
    same_style = _beverage_candidate(
        name="Fixture Bourbon Reserve",
        style="bourbon",
        vector_value=0.98,
    )
    different_style = _beverage_candidate(
        name="Fixture Scotch",
        style="single malt scotch whisky",
        vector_value=0.82,
    )
    service, _added = _beverage_service_with_candidates(
        (excluded, same_style, different_style),
    )

    response = service.get_beverage_recommendations(
        external_user_id="usr_123",
        exclude_beverage_ids=[str(excluded.beverage.id)],
        diversity_mode="different",
        limit=1,
    )

    assert response.results[0].target_id == str(different_style.beverage.id)
    assert (
        response.results[0].source_metadata["request_controls"]["diversity_mode"]
        == "different"
    )


def test_beverage_recommendations_adjacent_mode_same_category_new_style() -> None:
    excluded = _beverage_candidate(
        name="Fixture Bourbon",
        category="whiskey",
        style="bourbon",
        vector_value=1.0,
    )
    cross_category = _beverage_candidate(
        name="Fixture Red Wine",
        category="wine",
        style="full-bodied red wine",
        vector_value=0.99,
    )
    adjacent_style = _beverage_candidate(
        name="Fixture Irish",
        category="whiskey",
        style="Irish whiskey",
        vector_value=0.84,
    )
    service, _added = _beverage_service_with_candidates(
        (excluded, cross_category, adjacent_style),
    )

    response = service.get_beverage_recommendations(
        external_user_id="usr_123",
        exclude_beverage_ids=[str(excluded.beverage.id)],
        diversity_mode="adjacent",
        limit=1,
    )

    assert response.results[0].target_id == str(adjacent_style.beverage.id)


def test_beverage_recommendations_flavor_direction_changes_rank_and_logs() -> None:
    sweet = _beverage_candidate(
        name="Fixture Sweet Bourbon",
        category="whiskey",
        style="bourbon",
        vector_value=0.9,
    )
    _set_candidate_dimensions(
        sweet,
        {
            "sweet": 0.9,
            "smoky": 0.05,
            "body": 0.55,
            "alcohol_intensity": 0.45,
        },
    )
    smoky = _beverage_candidate(
        name="Fixture Smoky Scotch",
        category="whiskey",
        style="peated single malt",
        vector_value=0.2,
    )
    _set_candidate_dimensions(
        smoky,
        {
            "sweet": 0.2,
            "smoky": 0.9,
            "roasted": 0.45,
            "body": 0.65,
            "alcohol_intensity": 0.6,
        },
    )
    service, added = _beverage_service_with_candidates(
        (sweet, smoky),
        scoring_config=_beverage_scoring_v3(),
    )
    profile = _beverage_profile()
    profile.taste_vector = [0.5, 0.0, 0.0, 0.0, 0.5, *([0.0] * 11)]
    profile.taste_vector_json = {"sweet": 0.5, "smoky": 0.5}
    service._profiles = _FakeProfiles(profile)  # noqa: SLF001

    response = service.get_beverage_recommendations(
        external_user_id="usr_123",
        flavor_direction="smokier",
        limit=1,
    )

    assert response.results[0].target_id == str(smoky.beverage.id)
    assert "MATCHES_REQUESTED_FLAVOR_DIRECTION" in response.results[0].reason_codes
    direction_feature = response.results[0].source_metadata["model_features"][
        "flavor_direction_feature"
    ]
    assert direction_feature["policy"] == "beverage_flavor_direction_v1"
    assert direction_feature["direction"] == "smokier"
    assert direction_feature["fit"] > 0.6
    assert (
        response.results[0].source_metadata["request_controls"]["flavor_direction"]
        == "smokier"
    )

    request = _first_added(added, RecommendationRequest)
    assert request.filters_json["flavor_direction"] == "smokier"
    assert request.request_context_json["flavor_direction_policy"] == (
        "beverage_flavor_direction_v1"
    )
    result = _first_added(added, RecommendationResult)
    assert result.source_snapshot_json["request_controls"]["flavor_direction"] == (
        "smokier"
    )
    assert result.score_breakdown_json["flavor_direction_adjustment"] > 0


def test_beverage_recommendations_reject_invalid_flavor_direction() -> None:
    service, _added = _beverage_service_with_candidates(
        (
            _beverage_candidate(
                name="Fixture Bourbon",
                style="bourbon",
                vector_value=1.0,
            ),
        ),
    )

    with pytest.raises(ValueError, match="flavor_direction"):
        service.get_beverage_recommendations(
            external_user_id="usr_123",
            flavor_direction="extra_salty",
        )


def test_beverage_recommendations_suppresses_recent_dismiss_feedback() -> None:
    dismissed = _beverage_candidate(
        name="Fixture Dismissed Bourbon",
        style="bourbon",
        vector_value=1.0,
    )
    fallback = _beverage_candidate(
        name="Fixture Fallback Scotch",
        style="single malt scotch whisky",
        vector_value=0.9,
    )
    service, added = _beverage_service_with_candidates(
        (dismissed, fallback),
        feedback_rows=[(str(dismissed.beverage.id), "dismiss")],
    )

    response = service.get_beverage_recommendations(
        external_user_id="usr_123",
        limit=2,
    )

    assert [item.target_id for item in response.results] == [
        str(fallback.beverage.id),
    ]
    request = _first_added(added, RecommendationRequest)
    suppression = request.filters_json["feedback_suppression"]
    assert suppression["policy"] == "recent_dismiss_v1"
    assert suppression["suppressed_beverage_ids"] == [str(dismissed.beverage.id)]
    assert suppression["positive_beverage_ids"] == []
    assert request.request_context_json["feedback_suppressed_count"] == 1
    assert (
        response.results[0].source_metadata["request_controls"][
            "feedback_suppressed_count"
        ]
        == 1
    )


def test_beverage_recommendations_latest_positive_feedback_keeps_candidate() -> None:
    candidate = _beverage_candidate(
        name="A Fixture Saved Bourbon",
        style="bourbon",
        vector_value=1.0,
    )
    fallback = _beverage_candidate(
        name="Fixture Fallback Scotch",
        style="single malt scotch whisky",
        vector_value=0.9,
    )
    service, added = _beverage_service_with_candidates(
        (candidate, fallback),
        feedback_rows=[
            (str(candidate.beverage.id), "save"),
            (str(candidate.beverage.id), "dismiss"),
        ],
    )

    response = service.get_beverage_recommendations(
        external_user_id="usr_123",
        limit=2,
    )

    assert response.results[0].target_id == str(candidate.beverage.id)
    request = _first_added(added, RecommendationRequest)
    suppression = request.filters_json["feedback_suppression"]
    assert suppression["suppressed_beverage_ids"] == []
    assert suppression["positive_beverage_ids"] == [str(candidate.beverage.id)]
    assert request.request_context_json["feedback_positive_count"] == 1


def test_beverage_recommendations_exposes_image_metadata_for_flutter() -> None:
    candidate = _beverage_candidate(
        name="Fixture Image Bourbon",
        style="bourbon",
        vector_value=1.0,
    )
    candidate.beverage.metadata_json.update(
        {
            "image": {
                "policy_version": "beverage_image_v1",
                "image_kind": "category_representative",
                "image_url": "https://example.test/whiskey.jpg",
                "alt_text_ko": "위스키 잔 대표 이미지",
                "source_url": "https://example.test/source",
                "license": "Public Domain",
                "attribution": "Fixture photographer",
                "display_policy": "allowed_mvp_display_with_license_metadata",
                "review_status": "source_checked_mvp_seed",
            },
            "image_url": "https://example.test/whiskey.jpg",
            "image_alt_text_ko": "위스키 잔 대표 이미지",
        },
    )
    service, added = _beverage_service_with_candidates((candidate,))

    response = service.get_beverage_recommendations(
        external_user_id="usr_123",
        limit=1,
    )

    source_metadata = response.results[0].source_metadata
    assert source_metadata["image_url"] == "https://example.test/whiskey.jpg"
    assert source_metadata["image"]["license"] == "Public Domain"

    result = _first_added(added, RecommendationResult)
    assert result.source_snapshot_json["image"]["image_url"] == (
        "https://example.test/whiskey.jpg"
    )


def test_beverage_recommendations_exposes_budget_tradeoff_metadata() -> None:
    candidate = _beverage_candidate(
        name="Fixture Budget Bourbon",
        style="bourbon",
        vector_value=1.0,
        price_min_krw=35000,
        price_max_krw=45000,
        price_observation_count=2,
    )
    service, added = _beverage_service_with_candidates((candidate,))

    response = service.get_beverage_recommendations(
        external_user_id="usr_123",
        limit=1,
    )

    source_metadata = response.results[0].source_metadata
    assert source_metadata["budget_tradeoff"]["status"] == "within_budget"
    assert source_metadata["budget_tradeoff"]["source"] == (
        "catalog_price_not_live_offer"
    )
    assert (
        source_metadata["model_features"]["budget_tradeoff"]
        == source_metadata["budget_tradeoff"]
    )

    result = _first_added(added, RecommendationResult)
    assert result.source_snapshot_json["model_features"]["budget_tradeoff"][
        "policy_version"
    ] == "beverage_budget_tradeoff_v1"


def test_beverage_recommendations_uses_scoring_explanation_template_version() -> None:
    candidate = _beverage_candidate(
        name="Fixture Explanation Bourbon",
        style="bourbon",
        vector_value=1.0,
    )
    service, added = _beverage_service_with_candidates(
        (candidate,),
        scoring_config=_beverage_scoring_v3(),
    )

    response = service.get_beverage_recommendations(
        external_user_id="usr_123",
        limit=1,
    )

    assert "현재 취향 프로필" in response.results[0].explanation
    assert "is recommended because" not in response.results[0].explanation

    explanation = _first_added(added, RecommendationExplanation)
    assert explanation.template_version == "reason_template_v3"
    assert explanation.debug_json["template_version"] == "reason_template_v3"


def test_beverage_recommendations_reject_invalid_exclude_id() -> None:
    service, _added = _beverage_service_with_candidates(
        (
            _beverage_candidate(
                name="Fixture Bourbon",
                style="bourbon",
                vector_value=1.0,
            ),
        ),
    )

    with pytest.raises(ValueError, match="exclude_beverage_ids"):
        service.get_beverage_recommendations(
            external_user_id="usr_123",
            exclude_beverage_ids=["not-a-uuid"],
        )


class _FakeProfiles:
    def __init__(self, profile: TasteProfileRevision) -> None:
        self._profile = profile

    def get_active_profile_revision(self, external_user_id: str):
        return self._profile


class _FakeCatalog:
    def __init__(self, candidates: tuple[BeverageVectorCandidate, ...]) -> None:
        self._candidates = candidates

    def list_active_beverage_vector_candidates(
        self,
        *,
        vector_schema_version_id: uuid.UUID,
        category: str | None = None,
    ) -> tuple[BeverageVectorCandidate, ...]:
        if category:
            return tuple(
                candidate
                for candidate in self._candidates
                if candidate.beverage.category == category
            )
        return self._candidates


def _beverage_service_with_candidates(
    candidates: tuple[BeverageVectorCandidate, ...],
    *,
    result_rows: list[tuple[str]] | None = None,
    feedback_rows: list[tuple[str, str]] | None = None,
    scoring_config: ScoringConfig | None = None,
) -> tuple[BeverageRecommendationService, list[object]]:
    session = MagicMock(spec=Session)
    added: list[object] = []
    session.scalar.return_value = scoring_config or _beverage_scoring()
    session.add.side_effect = added.append
    execute_results = []
    if result_rows is not None:
        execute_results.append(_Rows(result_rows))
    execute_results.append(_Rows(feedback_rows or []))
    session.execute.side_effect = execute_results

    def flush() -> None:
        for item in added:
            if getattr(item, "id", None) is None:
                item.id = uuid.uuid4()

    session.flush.side_effect = flush
    service = BeverageRecommendationService(session)
    service._profiles = _FakeProfiles(_beverage_profile())  # noqa: SLF001
    service._catalog = _FakeCatalog(candidates)  # noqa: SLF001
    return service, added


class _Rows:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def all(self) -> list[tuple]:
        return self._rows


def _beverage_profile() -> TasteProfileRevision:
    vector_schema_id = uuid.UUID("99999999-9999-4999-8999-999999999999")
    return TasteProfileRevision(
        id=uuid.uuid4(),
        external_user_id="usr_123",
        profile_revision=1,
        survey_response_id="surv_resp_123",
        survey_version="survey_v1",
        survey_response_revision=1,
        mapper_version_id=uuid.uuid4(),
        vector_schema_version_id=vector_schema_id,
        taste_vector=[1.0, *([0.0] * 15)],
        taste_vector_json={"sweet": 1.0},
        confidence_json={},
        preferred_categories=["whiskey"],
        preferred_keywords=["vanilla_caramel"],
        budget_range="30000_50000",
        experience_level="beginner",
        status="active",
        generation_metadata_json={},
    )


def _beverage_candidate(
    *,
    name: str,
    style: str,
    vector_value: float,
    category: str = "whiskey",
    price_min_krw: int | None = None,
    price_max_krw: int | None = None,
    price_observation_count: int = 0,
) -> BeverageVectorCandidate:
    beverage_id = uuid.uuid4()
    metadata = {
        "catalog_key": f"{category}.{name.lower().replace(' ', '_')}",
        "style": style,
        "beginner_friendly_score": 0.8,
        "reason_code_hints": ["MATCHES_VANILLA_CARAMEL"],
        "source_version": "fixture_v1",
    }
    if price_min_krw is not None and price_max_krw is not None:
        metadata.update(
            {
                "price_policy": "verified_krw_observations_not_live_truth",
                "price_observation_summary": {
                    "market_region": "KR",
                    "currency": "KRW",
                    "observation_count": price_observation_count,
                    "price_min_krw": price_min_krw,
                    "price_max_krw": price_max_krw,
                },
            },
        )
    return BeverageVectorCandidate(
        beverage=BeverageItem(
            id=beverage_id,
            category=category,
            name_ko=name,
            name_en=name,
            price_min_krw=price_min_krw,
            price_max_krw=price_max_krw,
            active=True,
            metadata_json=metadata,
        ),
        vector=RecommendationVector(
            owner_type="beverage_item",
            owner_id=beverage_id,
            vector_schema_version_id=uuid.UUID(
                "99999999-9999-4999-8999-999999999999",
            ),
            vector=[vector_value, *([0.0] * 15)],
            vector_json={"sweet": vector_value},
            confidence_json={},
            source_hash=f"hash-{name}",
            source_metadata_json={},
        ),
        flavor_profile=None,
    )


def _set_candidate_dimensions(
    candidate: BeverageVectorCandidate,
    values: dict[str, float],
) -> None:
    by_name = {dimension.name: 0.0 for dimension in TASTE_V1_DIMENSIONS}
    by_name.update(values)
    candidate.vector.vector_json = by_name
    candidate.vector.vector = [
        by_name[dimension.name] for dimension in TASTE_V1_DIMENSIONS
    ]


def _beverage_scoring() -> ScoringConfig:
    return ScoringConfig(
        id=uuid.uuid4(),
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


def _beverage_scoring_v3() -> ScoringConfig:
    payload = next(
        item for item in scoring_v3_payloads() if item["target_type"] == "beverage"
    )
    return ScoringConfig(
        id=uuid.uuid4(),
        name=payload["name"],
        version=payload["version"],
        target_type=payload["target_type"],
        category=payload["category"],
        weights_json=payload["weights_json"],
        reason_code_rules_json=payload["reason_code_rules_json"],
        status=payload["status"],
    )


def _first_added(items: list[object], model_type):
    for item in items:
        if isinstance(item, model_type):
            return item
    raise AssertionError(f"{model_type.__name__} was not added")
