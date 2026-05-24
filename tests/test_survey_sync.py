from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.models.enums import ProfileStatus, SyncEventStatus
from app.models.profile import UserProfileState
from app.models.sync import DeadLetterEvent, SurveySyncCursor, SurveySyncEvent
from app.services.profile_generation import SurveyProfileInput
from app.services.survey_sync import (
    SurveyEventPage,
    SurveyResponse,
    SurveySyncRetryableError,
    SurveySyncService,
    parse_survey_event_page,
)


def test_parse_survey_event_page_validates_contract() -> None:
    page = parse_survey_event_page(
        {
            "cursor": "cur_1",
            "next_cursor": "cur_2",
            "has_more": True,
            "event_watermark": "2026-05-24T00:00:00Z",
            "events": [_event_payload()],
        },
    )

    assert page.next_cursor == "cur_2"
    assert page.has_more
    assert page.event_watermark == "2026-05-24T00:00:00Z"
    assert page.events[0].event_id == "survey_evt_1"


def test_survey_sync_advances_cursor_after_profile_event() -> None:
    cursor = SurveySyncCursor(
        source_name="survey-service",
        cursor_value="cur_1",
        metadata_json={},
    )
    session = MagicMock(spec=Session)
    session.scalar.side_effect = [cursor, None]
    client = _FakeSurveyClient(
        page=SurveyEventPage(
            cursor="cur_1",
            next_cursor="cur_2",
            has_more=False,
            event_watermark="2026-05-24T00:00:00Z",
            events=(parse_survey_event_page(_page_payload()).events[0],),
        ),
        response=_response(),
    )
    generator = _FakeProfileGenerator()

    result = SurveySyncService(session, client, generator).sync_once(limit=25)

    assert client.event_calls == [("cur_1", 25)]
    assert client.response_calls == [("surv_resp_1", 1)]
    assert generator.inputs[0].survey_response_id == "surv_resp_1"
    assert cursor.cursor_value == "cur_2"
    assert cursor.metadata_json["last_event_watermark"] == "2026-05-24T00:00:00Z"
    assert result.profiles_processed == 1
    assert result.events_processed == 1


def test_survey_sync_skips_processed_duplicate_event() -> None:
    cursor = SurveySyncCursor(
        source_name="survey-service",
        cursor_value="cur_1",
        metadata_json={},
    )
    processed = SurveySyncEvent(
        event_id="survey_evt_1",
        event_type="survey.response_completed",
        external_user_id="usr_1",
        survey_response_id="surv_resp_1",
        survey_version="survey_v1",
        response_revision=1,
        event_payload_json={},
        status=SyncEventStatus.PROCESSED.value,
        attempt_count=1,
    )
    session = MagicMock(spec=Session)
    session.scalar.side_effect = [cursor, processed]
    client = _FakeSurveyClient(
        page=SurveyEventPage(
            cursor="cur_1",
            next_cursor="cur_2",
            has_more=False,
            event_watermark="2026-05-24T00:00:00Z",
            events=(parse_survey_event_page(_page_payload()).events[0],),
        ),
        response=_response(),
    )
    generator = _FakeProfileGenerator()

    result = SurveySyncService(session, client, generator).sync_once()

    assert result.duplicate_events == 1
    assert generator.inputs == []
    assert client.response_calls == []


def test_survey_sync_revoked_event_marks_profile_state_stale() -> None:
    cursor = SurveySyncCursor(
        source_name="survey-service",
        cursor_value="cur_1",
        metadata_json={},
    )
    state = UserProfileState(
        external_user_id="usr_1",
        status=ProfileStatus.ACTIVE.value,
        last_survey_response_id="surv_resp_1",
        last_survey_response_revision=1,
    )
    session = MagicMock(spec=Session)
    session.scalar.side_effect = [cursor, None]
    session.get.return_value = state
    event = parse_survey_event_page(
        _page_payload(event_type="survey.response_revoked"),
    ).events[0]
    client = _FakeSurveyClient(
        page=SurveyEventPage(
            cursor="cur_1",
            next_cursor="cur_2",
            has_more=False,
            event_watermark="2026-05-24T00:00:00Z",
            events=(event,),
        ),
        response=_response(),
    )

    result = SurveySyncService(session, client, _FakeProfileGenerator()).sync_once()

    assert result.revoked_events == 1
    assert state.status == ProfileStatus.STALE.value
    assert state.last_survey_response_id == "surv_resp_1"
    assert client.response_calls == []


def test_survey_sync_dead_letters_unsupported_survey_version() -> None:
    cursor = SurveySyncCursor(
        source_name="survey-service",
        cursor_value="cur_1",
        metadata_json={},
    )
    session = MagicMock(spec=Session)
    session.scalar.side_effect = [cursor, None]
    event = parse_survey_event_page(_page_payload(survey_version="survey_v2")).events[0]
    client = _FakeSurveyClient(
        page=SurveyEventPage(
            cursor="cur_1",
            next_cursor="cur_2",
            has_more=False,
            event_watermark="2026-05-24T00:00:00Z",
            events=(event,),
        ),
        response=_response(),
    )

    result = SurveySyncService(session, client, _FakeProfileGenerator()).sync_once()

    sync_event = _added_sync_event(session)
    dead_letter = _added_dead_letter(session)
    assert sync_event.status == SyncEventStatus.DEAD_LETTER.value
    assert "unsupported survey version" in sync_event.last_error
    assert dead_letter.event_id == "survey_evt_1"
    assert "unsupported survey version" in dead_letter.dead_letter_reason
    assert result.dead_letter_events == 1
    assert client.response_calls == []


def test_survey_sync_retry_does_not_advance_cursor() -> None:
    cursor = SurveySyncCursor(
        source_name="survey-service",
        cursor_value="cur_1",
        metadata_json={},
    )
    session = MagicMock(spec=Session)
    session.scalar.side_effect = [cursor, None]
    client = _FakeSurveyClient(
        page=SurveyEventPage(
            cursor="cur_1",
            next_cursor="cur_2",
            has_more=False,
            event_watermark="2026-05-24T00:00:00Z",
            events=(parse_survey_event_page(_page_payload()).events[0],),
        ),
        response=SurveySyncRetryableError("survey-service unavailable"),
    )

    with pytest.raises(SurveySyncRetryableError):
        SurveySyncService(
            session,
            client,
            _FakeProfileGenerator(),
            retry_base_seconds=5,
        ).sync_once()

    sync_event = _added_sync_event(session)
    assert sync_event.status == SyncEventStatus.RETRY.value
    assert sync_event.last_error == "survey-service unavailable"
    assert sync_event.next_retry_at is not None
    assert cursor.cursor_value == "cur_1"


def _page_payload(
    *,
    event_type: str = "survey.response_completed",
    survey_version: str = "survey_v1",
) -> dict[str, object]:
    return {
        "cursor": "cur_1",
        "next_cursor": "cur_2",
        "has_more": False,
        "event_watermark": "2026-05-24T00:00:00Z",
        "events": [
            _event_payload(event_type=event_type, survey_version=survey_version),
        ],
    }


def _event_payload(
    *,
    event_type: str = "survey.response_completed",
    survey_version: str = "survey_v1",
) -> dict[str, object]:
    return {
        "event_id": "survey_evt_1",
        "event_type": event_type,
        "occurred_at": "2026-05-24T00:00:00Z",
        "external_user_id": "usr_1",
        "survey_response_id": "surv_resp_1",
        "survey_version": survey_version,
        "response_revision": 1,
    }


def _response() -> SurveyResponse:
    return SurveyResponse(
        survey_response_id="surv_resp_1",
        external_user_id="usr_1",
        survey_version="survey_v1",
        response_revision=1,
        completed_at=datetime(2026, 5, 24, tzinfo=UTC),
        answers={
            "categories": ["whiskey"],
            "global_keywords": ["vanilla_caramel"],
            "category_traits": {"whiskey": ["oak_woody"]},
            "budget_range": "30000_100000",
            "experience_level": "beginner",
        },
        payload={},
    )


def _added_sync_event(session: MagicMock) -> SurveySyncEvent:
    for call in session.add.call_args_list:
        added = call.args[0]
        if isinstance(added, SurveySyncEvent):
            return added
    raise AssertionError("SurveySyncEvent was not added")


def _added_dead_letter(session: MagicMock) -> DeadLetterEvent:
    for call in session.add.call_args_list:
        added = call.args[0]
        if isinstance(added, DeadLetterEvent):
            return added
    raise AssertionError("DeadLetterEvent was not added")


class _FakeSurveyClient:
    def __init__(
        self,
        *,
        page: SurveyEventPage,
        response: SurveyResponse | Exception,
    ) -> None:
        self._page = page
        self._response = response
        self.event_calls: list[tuple[str | None, int]] = []
        self.response_calls: list[tuple[str, int]] = []

    def list_survey_events(
        self,
        *,
        cursor: str | None,
        limit: int,
    ) -> SurveyEventPage:
        self.event_calls.append((cursor, limit))
        return self._page

    def get_survey_response(
        self,
        *,
        survey_response_id: str,
        response_revision: int,
    ) -> SurveyResponse:
        self.response_calls.append((survey_response_id, response_revision))
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _FakeProfileGenerator:
    def __init__(self) -> None:
        self.inputs: list[SurveyProfileInput] = []

    def generate_from_survey_input(self, survey_input: SurveyProfileInput):
        self.inputs.append(survey_input)
        return object()
