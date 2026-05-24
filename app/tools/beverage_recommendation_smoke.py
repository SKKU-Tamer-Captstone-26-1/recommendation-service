"""Smoke beverage recommendations from PostgreSQL after catalog/index rebuild."""

from __future__ import annotations

import argparse
import uuid
from datetime import UTC, datetime

from app.db.session import SessionLocal
from app.models.recommendation_event import RecommendationResult
from app.repositories.profiles import ProfileRepository
from app.services.profile_generation import (
    ProfileGenerationService,
    SurveyProfileInput,
)
from app.services.recommendations import BeverageRecommendationService

SMOKE_USER_ID = "smoke_beverage_recommendation_user"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default="whiskey")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    with SessionLocal() as session:
        _ensure_profile(session, datetime.now(UTC))
        response = BeverageRecommendationService(session).get_beverage_recommendations(
            external_user_id=SMOKE_USER_ID,
            category=args.category,
            limit=args.limit,
        )
        session.commit()

    if not response.results:
        raise RuntimeError("GetBeverageRecommendations returned no recommendations")

    first = response.results[0]
    result_id = uuid.UUID(str(first.result_id))
    with SessionLocal() as session:
        result = session.get(RecommendationResult, result_id)
        if result is None:
            raise RuntimeError(f"recommendation result not found: {result_id}")
        source = result.source_snapshot_json
        if source.get("candidate_source") != "postgres_catalog":
            raise RuntimeError(
                "beverage recommendation did not use PostgreSQL catalog source",
            )
        if source.get("model_features") is None:
            raise RuntimeError("beverage recommendation missing model_features")

    print(
        "beverage recommendation smoke "
        f"request_id={response.request_id} "
        f"result_id={result_id} "
        f"catalog_key={first.source_metadata.get('catalog_key')} "
        f"category={first.category} "
        f"score={first.final_score} "
        "candidate_source=postgres_catalog",
    )
    return 0


def _ensure_profile(session, now: datetime) -> None:
    profile = ProfileRepository(session).get_active_profile_revision(SMOKE_USER_ID)
    if profile is not None:
        return
    ProfileGenerationService(session).generate_from_survey_input(
        SurveyProfileInput(
            survey_response_id="smoke_beverage_recommendation_survey",
            external_user_id=SMOKE_USER_ID,
            survey_version="survey_v1",
            response_revision=1,
            completed_at=now,
            answers={
                "categories": ["whiskey"],
                "global_keywords": ["vanilla_caramel", "oak_woody"],
                "category_traits": {"whiskey": ["vanilla_caramel", "oak_woody"]},
                "budget_range": "30000_100000",
                "experience_level": "beginner",
            },
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
