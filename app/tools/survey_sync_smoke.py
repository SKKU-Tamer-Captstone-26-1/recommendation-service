"""Smoke survey sync through profile generation and recommendation logging."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.db.session import SessionLocal
from app.grpc.gen import recommendation_pb2
from app.grpc.recommendation_service import RecommendationGrpcServicer
from app.models.recommendation_event import RecommendationRequest
from app.repositories.profiles import ProfileRepository
from app.services.auth import StaticAuthContextResolver
from app.services.survey_sync import (
    SurveyEvent,
    SurveyEventPage,
    SurveyResponse,
    SurveySyncService,
)

SMOKE_USER_ID = "smoke_survey_sync_user"


def main() -> int:
    now = datetime.now(UTC)
    date_key = now.strftime("%Y%m%d")
    survey_response_id = f"smoke_survey_response_{date_key}"

    client = _SmokeSurveyClient(
        now=now,
        survey_response_id=survey_response_id,
    )
    with SessionLocal() as session:
        sync_result = SurveySyncService(session, client).sync_once(
            source_name="survey-service-smoke",
            limit=10,
        )
        session.commit()

    servicer = RecommendationGrpcServicer(
        SessionLocal,
        StaticAuthContextResolver(SMOKE_USER_ID),
    )
    response = servicer.GetBeverageRecommendations(
        recommendation_pb2.GetBeverageRecommendationsRequest(
            category="",
            limit=3,
            budget_mode=recommendation_pb2.BUDGET_MODE_SOFT,
        ),
        _SmokeGrpcContext(),
    )
    if not response.request_id:
        raise RuntimeError("GetBeverageRecommendations did not create a request log")

    with SessionLocal() as session:
        profile = ProfileRepository(session).get_active_profile_revision(SMOKE_USER_ID)
        if profile is None:
            raise RuntimeError("survey sync did not create an active profile")
        request = session.get(RecommendationRequest, UUID(response.request_id))
        if request is None:
            raise RuntimeError(f"recommendation request missing: {response.request_id}")
        if request.profile_revision_id != profile.id:
            raise RuntimeError(
                "recommendation request profile revision mismatch: "
                f"expected={profile.id} actual={request.profile_revision_id}",
            )

    print(
        "survey sync smoke "
        f"request_id={response.request_id} "
        f"profile_revision_id={profile.id} "
        f"survey_response_id={survey_response_id} "
        f"events={sync_result.events_received} "
        f"profiles={sync_result.profiles_processed} "
        f"duplicates={sync_result.duplicate_events}",
    )
    return 0


class _SmokeSurveyClient:
    def __init__(self, *, now: datetime, survey_response_id: str) -> None:
        date_key = now.strftime("%Y%m%d")
        self._event = SurveyEvent(
            event_id=f"smoke_survey_evt_{date_key}",
            event_type="survey.response_completed",
            occurred_at=now,
            external_user_id=SMOKE_USER_ID,
            survey_response_id=survey_response_id,
            survey_version="survey_v1",
            response_revision=1,
            payload={
                "event_id": f"smoke_survey_evt_{date_key}",
                "event_type": "survey.response_completed",
                "occurred_at": now.isoformat(),
                "external_user_id": SMOKE_USER_ID,
                "survey_response_id": survey_response_id,
                "survey_version": "survey_v1",
                "response_revision": 1,
            },
        )
        self._response = SurveyResponse(
            survey_response_id=survey_response_id,
            external_user_id=SMOKE_USER_ID,
            survey_version="survey_v1",
            response_revision=1,
            completed_at=now,
            answers={
                "categories": ["whiskey"],
                "global_keywords": ["vanilla_caramel", "oak_woody"],
                "category_traits": {"whiskey": ["vanilla_caramel", "oak_woody"]},
                "budget_range": "under_70000",
                "experience_level": "beginner",
            },
            payload={},
        )

    def list_survey_events(
        self,
        *,
        cursor: str | None,
        limit: int,
    ) -> SurveyEventPage:
        return SurveyEventPage(
            cursor=cursor,
            next_cursor=self._event.event_id,
            has_more=False,
            event_watermark=self._event.occurred_at.isoformat(),
            events=(self._event,),
        )

    def get_survey_response(
        self,
        *,
        survey_response_id: str,
        response_revision: int,
    ) -> SurveyResponse:
        if (
            survey_response_id != self._response.survey_response_id
            or response_revision != self._response.response_revision
        ):
            raise RuntimeError("unexpected smoke survey response lookup")
        return self._response


class _SmokeGrpcContext:
    def invocation_metadata(self) -> tuple[object, ...]:
        return ()

    def abort(self, code, details):
        raise RuntimeError(f"{code.name}: {details}")


if __name__ == "__main__":
    raise SystemExit(main())
