from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import grpc
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.grpc.gen import survey_pb2, survey_pb2_grpc
from app.models.enums import ProfileStatus, SyncEventStatus
from app.models.profile import UserProfileState
from app.models.sync import DeadLetterEvent, SurveySyncCursor, SurveySyncEvent
from app.services.profile_generation import (
    ProfileGenerationService,
    SurveyProfileInput,
    canonicalize_survey_budget_range,
    canonicalize_survey_categories,
    canonicalize_survey_category,
)

PROFILE_EVENT_TYPES = frozenset(
    {"survey.response_completed", "survey.response_updated"},
)
SUPPORTED_SURVEY_EVENT_TYPES = frozenset(
    {
        "survey.response_completed",
        "survey.response_updated",
        "survey.response_revoked",
        "survey.schema_published",
    },
)
SUPPORTED_SURVEY_VERSIONS = frozenset({"survey_v1"})
DEPLOYED_SURVEY_RESULT_ADAPTER_VERSION = "survey_v1"


class SurveySyncRetryableError(RuntimeError):
    """Raised when a survey sync event/page should be retried."""


@dataclass(frozen=True)
class SurveyEvent:
    event_id: str
    event_type: str
    occurred_at: datetime
    external_user_id: str
    survey_response_id: str
    survey_version: str
    response_revision: int
    payload: dict[str, Any]


@dataclass(frozen=True)
class SurveyResponse:
    survey_response_id: str
    external_user_id: str
    survey_version: str
    response_revision: int
    completed_at: datetime
    answers: dict[str, Any]
    payload: dict[str, Any]


@dataclass(frozen=True)
class SurveyEventPage:
    cursor: str | None
    next_cursor: str | None
    has_more: bool
    event_watermark: str
    events: tuple[SurveyEvent, ...]


@dataclass(frozen=True)
class SurveyEventProcessResult:
    event_id: str
    duplicate_event: bool = False
    profile_processed: bool = False
    revoked_profile: bool = False
    schema_event: bool = False
    dead_lettered: bool = False
    retry_scheduled: bool = False


@dataclass(frozen=True)
class SurveySyncResult:
    source_name: str
    previous_cursor: str | None
    next_cursor: str | None
    has_more: bool
    event_watermark: str
    events_received: int
    events_processed: int
    duplicate_events: int
    profiles_processed: int
    revoked_events: int
    schema_events: int
    dead_letter_events: int
    retry_events: int


class SurveySyncClient(Protocol):
    def list_survey_events(
        self,
        *,
        cursor: str | None,
        limit: int,
    ) -> SurveyEventPage:
        """Return one page of survey-service events."""

    def get_survey_response(
        self,
        *,
        survey_response_id: str,
        response_revision: int,
    ) -> SurveyResponse:
        """Return one canonical survey response revision from survey-service."""


class ProfileGenerator(Protocol):
    def generate_from_survey_input(self, survey_input: SurveyProfileInput): ...


class HttpSurveySyncClient:
    """HTTP fallback client for the survey-service event/response API contract."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client or httpx.Client(
            base_url=self._settings.survey_service_url,
            timeout=self._settings.survey_request_timeout_seconds,
        )

    def list_survey_events(
        self,
        *,
        cursor: str | None,
        limit: int,
    ) -> SurveyEventPage:
        params: dict[str, str | int] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        response = self._client.get(self._settings.survey_events_path, params=params)
        response.raise_for_status()
        return parse_survey_event_page(response.json())

    def get_survey_response(
        self,
        *,
        survey_response_id: str,
        response_revision: int,
    ) -> SurveyResponse:
        path = self._settings.survey_response_path_template.format(
            survey_response_id=survey_response_id,
        )
        response = self._client.get(
            path,
            params={"response_revision": response_revision},
        )
        response.raise_for_status()
        return parse_survey_response(response.json())


class SurveyResultGrpcAdapterClient:
    """One-shot adapter for the currently deployed survey-service result RPCs.

    This is not a replacement for the cursor-based sync contract. It exists so a
    safe test user can be bridged while survey-service adds event/response sync
    RPCs for production.
    """

    def __init__(
        self,
        *,
        address: str,
        use_tls: bool | None = None,
        bearer_token: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._address = address
        self._use_tls = use_tls if use_tls is not None else address.endswith(":443")
        self._bearer_token = bearer_token
        self._timeout_seconds = timeout_seconds

    def get_survey_result_by_user(self, *, external_user_id: str) -> SurveyResponse:
        if not external_user_id:
            raise ValueError("external_user_id is required")
        with self._channel() as channel:
            stub = survey_pb2_grpc.SurveyServiceStub(channel)
            response = stub.GetSurveyResultByUser(
                survey_pb2.GetSurveyResultByUserRequest(user_id=external_user_id),
                timeout=self._timeout_seconds,
                metadata=self._metadata(),
            )
        return survey_result_to_response(response.result)

    def get_survey_result(self, *, survey_response_id: str) -> SurveyResponse:
        if not survey_response_id:
            raise ValueError("survey_response_id is required")
        with self._channel() as channel:
            stub = survey_pb2_grpc.SurveyServiceStub(channel)
            response = stub.GetSurveyResult(
                survey_pb2.GetSurveyResultRequest(survey_id=survey_response_id),
                timeout=self._timeout_seconds,
                metadata=self._metadata(),
            )
        return survey_result_to_response(response.result)

    def _channel(self) -> grpc.Channel:
        if self._use_tls:
            return grpc.secure_channel(self._address, grpc.ssl_channel_credentials())
        return grpc.insecure_channel(self._address)

    def _metadata(self) -> tuple[tuple[str, str], ...]:
        if not self._bearer_token:
            return ()
        return (("authorization", f"Bearer {self._bearer_token}"),)


class SurveySyncService:
    """Pulls survey-service events and regenerates derived profiles."""

    def __init__(
        self,
        session: Session,
        client: SurveySyncClient,
        profile_generator: ProfileGenerator | None = None,
        *,
        max_attempts: int | None = None,
        retry_base_seconds: int | None = None,
    ) -> None:
        settings = get_settings()
        self._session = session
        self._client = client
        self._profile_generator = profile_generator or ProfileGenerationService(session)
        self._max_attempts = max_attempts or settings.sync_max_attempts
        self._retry_base_seconds = (
            retry_base_seconds or settings.sync_retry_base_seconds
        )

    def sync_once(
        self,
        *,
        source_name: str = "survey-service",
        limit: int | None = None,
    ) -> SurveySyncResult:
        settings = get_settings()
        resolved_limit = limit or settings.survey_events_page_size
        if resolved_limit <= 0:
            raise ValueError("limit must be greater than zero")

        cursor = self._get_or_create_cursor(source_name)
        previous_cursor = cursor.cursor_value
        page = self._client.list_survey_events(
            cursor=previous_cursor,
            limit=resolved_limit,
        )

        results: list[SurveyEventProcessResult] = []
        for event in page.events:
            results.append(self.process_event(event))

        cursor.cursor_value = page.next_cursor
        cursor.last_synced_at = datetime.now(UTC)
        cursor.metadata_json = {
            **(cursor.metadata_json or {}),
            "last_page_cursor": page.cursor,
            "last_event_watermark": page.event_watermark,
            "last_events_received": len(page.events),
            "last_events_processed": len(results),
            "has_more": page.has_more,
        }
        self._session.add(cursor)
        self._session.flush()

        return SurveySyncResult(
            source_name=source_name,
            previous_cursor=previous_cursor,
            next_cursor=page.next_cursor,
            has_more=page.has_more,
            event_watermark=page.event_watermark,
            events_received=len(page.events),
            events_processed=len(results),
            duplicate_events=sum(1 for item in results if item.duplicate_event),
            profiles_processed=sum(1 for item in results if item.profile_processed),
            revoked_events=sum(1 for item in results if item.revoked_profile),
            schema_events=sum(1 for item in results if item.schema_event),
            dead_letter_events=sum(1 for item in results if item.dead_lettered),
            retry_events=sum(1 for item in results if item.retry_scheduled),
        )

    def process_event(self, event: SurveyEvent) -> SurveyEventProcessResult:
        sync_event = self._get_or_create_event(event)
        if sync_event.status in {
            SyncEventStatus.PROCESSED.value,
            SyncEventStatus.DEAD_LETTER.value,
        }:
            return SurveyEventProcessResult(
                event_id=event.event_id,
                duplicate_event=True,
            )

        sync_event.status = SyncEventStatus.PROCESSING.value
        sync_event.attempt_count = (sync_event.attempt_count or 0) + 1
        sync_event.last_error = None
        self._session.add(sync_event)
        self._session.flush()

        try:
            if event.event_type not in SUPPORTED_SURVEY_EVENT_TYPES:
                return self._mark_dead_letter(
                    sync_event,
                    reason=f"unsupported survey event type: {event.event_type}",
                )
            if event.event_type in PROFILE_EVENT_TYPES:
                return self._process_profile_event(sync_event, event)
            if event.event_type == "survey.response_revoked":
                self._mark_profile_stale(event)
                self._mark_processed(sync_event)
                return SurveyEventProcessResult(
                    event_id=event.event_id,
                    revoked_profile=True,
                )
            self._mark_processed(sync_event)
            return SurveyEventProcessResult(event_id=event.event_id, schema_event=True)
        except Exception as exc:
            if _is_retryable_error(exc):
                return self._mark_retry_or_dead_letter(sync_event, exc)
            return self._mark_dead_letter(sync_event, reason=str(exc))

    def _process_profile_event(
        self,
        sync_event: SurveySyncEvent,
        event: SurveyEvent,
    ) -> SurveyEventProcessResult:
        if event.survey_version not in SUPPORTED_SURVEY_VERSIONS:
            return self._mark_dead_letter(
                sync_event,
                reason=f"unsupported survey version: {event.survey_version}",
            )
        response = self._client.get_survey_response(
            survey_response_id=event.survey_response_id,
            response_revision=event.response_revision,
        )
        _validate_response_matches_event(response, event)
        self._profile_generator.generate_from_survey_input(
            SurveyProfileInput(
                survey_response_id=response.survey_response_id,
                external_user_id=response.external_user_id,
                survey_version=response.survey_version,
                response_revision=response.response_revision,
                completed_at=response.completed_at,
                answers=response.answers,
            ),
        )
        self._mark_processed(sync_event)
        return SurveyEventProcessResult(
            event_id=event.event_id,
            profile_processed=True,
        )

    def _get_or_create_cursor(self, source_name: str) -> SurveySyncCursor:
        cursor = self._session.scalar(
            select(SurveySyncCursor).where(SurveySyncCursor.source_name == source_name),
        )
        if cursor is not None:
            return cursor
        cursor = SurveySyncCursor(
            source_name=source_name,
            cursor_value=None,
            metadata_json={},
        )
        self._session.add(cursor)
        self._session.flush()
        return cursor

    def _get_or_create_event(self, event: SurveyEvent) -> SurveySyncEvent:
        sync_event = self._session.scalar(
            select(SurveySyncEvent).where(SurveySyncEvent.event_id == event.event_id),
        )
        if sync_event is not None:
            return sync_event
        sync_event = SurveySyncEvent(
            event_id=event.event_id,
            event_type=event.event_type,
            external_user_id=event.external_user_id,
            survey_response_id=event.survey_response_id,
            survey_version=event.survey_version,
            response_revision=event.response_revision,
            event_payload_json=event.payload,
            status=SyncEventStatus.PENDING.value,
            attempt_count=0,
        )
        self._session.add(sync_event)
        self._session.flush()
        return sync_event

    def _mark_processed(self, sync_event: SurveySyncEvent) -> None:
        sync_event.status = SyncEventStatus.PROCESSED.value
        sync_event.processed_at = datetime.now(UTC)
        sync_event.next_retry_at = None
        sync_event.last_error = None
        self._session.flush()

    def _mark_retry_or_dead_letter(
        self,
        sync_event: SurveySyncEvent,
        exc: Exception,
    ) -> SurveyEventProcessResult:
        if sync_event.attempt_count >= self._max_attempts:
            return self._mark_dead_letter(sync_event, reason=str(exc))
        sync_event.status = SyncEventStatus.RETRY.value
        sync_event.last_error = str(exc)
        sync_event.next_retry_at = datetime.now(UTC) + timedelta(
            seconds=self._retry_base_seconds * max(1, sync_event.attempt_count),
        )
        self._session.flush()
        raise SurveySyncRetryableError(str(exc)) from exc

    def _mark_dead_letter(
        self,
        sync_event: SurveySyncEvent,
        *,
        reason: str,
    ) -> SurveyEventProcessResult:
        sync_event.status = SyncEventStatus.DEAD_LETTER.value
        sync_event.last_error = reason
        sync_event.next_retry_at = None
        self._session.add(
            DeadLetterEvent(
                sync_event_id=sync_event.id,
                event_id=sync_event.event_id,
                event_type=sync_event.event_type,
                event_payload_json=sync_event.event_payload_json,
                dead_letter_reason=reason,
                last_error=reason,
                attempt_count=sync_event.attempt_count,
            ),
        )
        self._session.flush()
        return SurveyEventProcessResult(
            event_id=sync_event.event_id,
            dead_lettered=True,
        )

    def _mark_profile_stale(self, event: SurveyEvent) -> None:
        state = self._session.get(UserProfileState, event.external_user_id)
        if state is None:
            state = UserProfileState(
                external_user_id=event.external_user_id,
                status=ProfileStatus.STALE.value,
                last_survey_response_id=event.survey_response_id,
                last_survey_response_revision=event.response_revision,
            )
            self._session.add(state)
        state.status = ProfileStatus.STALE.value
        state.last_survey_response_id = event.survey_response_id
        state.last_survey_response_revision = event.response_revision
        self._session.flush()


def parse_survey_event_page(payload: Any) -> SurveyEventPage:
    if not isinstance(payload, dict):
        raise ValueError("survey event page must be an object")
    has_more = payload.get("has_more")
    if not isinstance(has_more, bool):
        raise ValueError("has_more must be a boolean")
    next_cursor = _optional_str(payload, "next_cursor")
    if has_more and next_cursor is None:
        raise ValueError("next_cursor is required when has_more is true")
    events = payload.get("events")
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    return SurveyEventPage(
        cursor=_optional_str(payload, "cursor"),
        next_cursor=next_cursor,
        has_more=has_more,
        event_watermark=_required_str(payload, "event_watermark"),
        events=tuple(parse_survey_event(event) for event in events),
    )


def parse_survey_event(payload: Any) -> SurveyEvent:
    if not isinstance(payload, dict):
        raise ValueError("survey event must be an object")
    response_revision = payload.get("response_revision")
    if not isinstance(response_revision, int) or response_revision <= 0:
        raise ValueError("response_revision must be a positive integer")
    return SurveyEvent(
        event_id=_required_str(payload, "event_id"),
        event_type=_required_str(payload, "event_type"),
        occurred_at=_parse_datetime(payload.get("occurred_at"), "occurred_at"),
        external_user_id=_required_str(payload, "external_user_id"),
        survey_response_id=_required_str(payload, "survey_response_id"),
        survey_version=_required_str(payload, "survey_version"),
        response_revision=response_revision,
        payload=payload,
    )


def parse_survey_response(payload: Any) -> SurveyResponse:
    if not isinstance(payload, dict):
        raise ValueError("survey response must be an object")
    response_revision = payload.get("response_revision")
    if not isinstance(response_revision, int) or response_revision <= 0:
        raise ValueError("response_revision must be a positive integer")
    answers = payload.get("answers")
    if not isinstance(answers, dict):
        raise ValueError("answers must be an object")
    return SurveyResponse(
        survey_response_id=_required_str(payload, "survey_response_id"),
        external_user_id=_required_str(payload, "external_user_id"),
        survey_version=_required_str(payload, "survey_version"),
        response_revision=response_revision,
        completed_at=_parse_datetime(payload.get("completed_at"), "completed_at"),
        answers=answers,
        payload=payload,
    )


def survey_result_to_response(result: survey_pb2.SurveyResult) -> SurveyResponse:
    if not result.survey_id:
        raise ValueError("survey result is missing survey_id")
    if not result.user_id:
        raise ValueError("survey result is missing user_id")
    completed_at = (
        result.submitted_at.ToDatetime(tzinfo=UTC)
        if result.HasField("submitted_at")
        else datetime.now(UTC)
    )
    answers = {
        "experience_level": result.level or None,
        "categories": canonicalize_survey_categories(list(result.categories)),
        "category_traits": _category_traits_from_survey_result(result),
        "global_keywords": list(result.flavor_keywords),
        "budget_range": canonicalize_survey_budget_range(result.budget),
        "source_contract": "ontheblock.survey.v1.SurveyResult",
    }
    payload = {
        "survey_response_id": result.survey_id,
        "external_user_id": result.user_id,
        "survey_version": DEPLOYED_SURVEY_RESULT_ADAPTER_VERSION,
        "response_revision": 1,
        "completed_at": completed_at,
        "answers": answers,
    }
    return SurveyResponse(
        survey_response_id=result.survey_id,
        external_user_id=result.user_id,
        survey_version=DEPLOYED_SURVEY_RESULT_ADAPTER_VERSION,
        response_revision=1,
        completed_at=completed_at,
        answers=answers,
        payload=payload,
    )


def _category_traits_from_survey_result(
    result: survey_pb2.SurveyResult,
) -> dict[str, list[str]]:
    traits: dict[str, list[str]] = {}
    for category, values in (
        ("whiskey", result.whiskey),
        ("wine", result.wine),
        ("cocktail", result.cocktail),
        ("beer", result.beer),
    ):
        parsed = [value for value in values if value]
        if parsed:
            traits[canonicalize_survey_category(category)] = parsed
    return traits


def _validate_response_matches_event(
    response: SurveyResponse,
    event: SurveyEvent,
) -> None:
    expected = {
        "survey_response_id": event.survey_response_id,
        "external_user_id": event.external_user_id,
        "survey_version": event.survey_version,
        "response_revision": event.response_revision,
    }
    actual = {
        "survey_response_id": response.survey_response_id,
        "external_user_id": response.external_user_id,
        "survey_version": response.survey_version,
        "response_revision": response.response_revision,
    }
    if actual != expected:
        raise ValueError("survey response does not match sync event")


def _is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, SurveySyncRetryableError | httpx.RequestError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code == 404 or status_code >= 500
    return False


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} is required")
    return value


def _optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _parse_datetime(value: Any, key: str) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
