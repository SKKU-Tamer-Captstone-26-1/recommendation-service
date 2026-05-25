from __future__ import annotations

import uuid
from collections.abc import Callable
from time import perf_counter

import grpc
from google.protobuf import json_format
from sqlalchemy.orm import Session

from app.grpc.gen import recommendation_pb2, recommendation_pb2_grpc
from app.services.auth import AuthContextResolver, AuthError, metadata_to_dict
from app.services.recommendations import (
    BeverageRecommendationService,
    RecommendationPreconditionError,
)
from app.services.runtime_metrics import runtime_metrics


class RecommendationGrpcServicer(recommendation_pb2_grpc.RecommendationServiceServicer):
    def __init__(
        self,
        session_factory: Callable[[], Session],
        auth_resolver: AuthContextResolver,
    ) -> None:
        self._session_factory = session_factory
        self._auth_resolver = auth_resolver

    def GetProfileStatus(self, request, context):
        started_at = perf_counter()
        try:
            external_user_id = self._resolve_external_user_id(context)
            with self._session_factory() as session:
                service = BeverageRecommendationService(session)
                status = service.get_profile_status(external_user_id)
                response = recommendation_pb2.GetProfileStatusResponse(
                    status=_profile_status_to_proto(status.status),
                    profile_revision=status.profile_revision or 0,
                    survey_response_id=status.survey_response_id or "",
                    stale_reason=status.stale_reason or "",
                )
                if status.generated_at:
                    response.generated_at.FromDatetime(status.generated_at)
                _record_grpc_status("GetProfileStatus", "ok", started_at)
                return response
        except Exception:
            _record_grpc_status("GetProfileStatus", "error", started_at)
            raise

    def GetBeverageRecommendations(self, request, context):
        started_at = perf_counter()
        session = None
        try:
            external_user_id = self._resolve_external_user_id(context)
            budget_mode = _budget_mode_from_proto(request.budget_mode)
            session = self._session_factory()
            service = BeverageRecommendationService(session)
            response = service.get_beverage_recommendations(
                external_user_id=external_user_id,
                category=request.category or None,
                limit=request.limit or None,
                budget_mode=budget_mode,
            )
            session.commit()
            _record_grpc_status("GetBeverageRecommendations", "ok", started_at)
            return recommendation_pb2.GetBeverageRecommendationsResponse(
                request_id=str(response.request_id) if response.request_id else "",
                profile_status=_profile_status_to_proto(response.profile_status),
                profile_revision=response.profile_revision or 0,
                recommendations=[
                    _recommendation_to_proto(item) for item in response.results
                ],
            )
        except RecommendationPreconditionError as exc:
            if session is not None:
                session.rollback()
            _record_grpc_status(
                "GetBeverageRecommendations",
                "failed_precondition",
                started_at,
            )
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(exc))
        except Exception:
            if session is not None:
                session.rollback()
            _record_grpc_status("GetBeverageRecommendations", "error", started_at)
            raise
        finally:
            if session is not None:
                session.close()

    def GetVenueRecommendations(self, request, context):
        started_at = perf_counter()
        session = None
        try:
            external_user_id = self._resolve_external_user_id(context)
            budget_mode = _budget_mode_from_proto(request.budget_mode)
            session = self._session_factory()
            service = BeverageRecommendationService(session)
            response = service.get_venue_recommendations(
                external_user_id=external_user_id,
                selected_beverage_id=request.selected_beverage_id,
                lat=request.lat,
                lng=request.lng,
                radius_m=request.radius_m or None,
                limit=request.limit or None,
                budget_mode=budget_mode,
            )
            session.commit()
            _record_grpc_status("GetVenueRecommendations", "ok", started_at)
            return recommendation_pb2.GetVenueRecommendationsResponse(
                request_id=str(response.request_id) if response.request_id else "",
                profile_status=_profile_status_to_proto(response.profile_status),
                profile_revision=response.profile_revision or 0,
                recommendations=[
                    _venue_recommendation_to_proto(item) for item in response.results
                ],
            )
        except RecommendationPreconditionError as exc:
            if session is not None:
                session.rollback()
            _record_grpc_status(
                "GetVenueRecommendations",
                "failed_precondition",
                started_at,
            )
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(exc))
        except ValueError as exc:
            if session is not None:
                session.rollback()
            _record_grpc_status(
                "GetVenueRecommendations",
                "invalid_argument",
                started_at,
            )
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        except Exception:
            if session is not None:
                session.rollback()
            _record_grpc_status("GetVenueRecommendations", "error", started_at)
            raise
        finally:
            if session is not None:
                session.close()

    def RecordRecommendationEvent(self, request, context):
        started_at = perf_counter()
        session = None
        try:
            self._resolve_external_user_id(context)
            metadata = json_format.MessageToDict(
                request.metadata,
                preserving_proto_field_name=True,
            )
            result_id = uuid.UUID(request.result_id) if request.result_id else None
            session = self._session_factory()
            service = BeverageRecommendationService(session)
            response = service.record_interaction(
                request_id=uuid.UUID(request.request_id),
                result_id=result_id,
                event_type=_event_type_from_proto(request.event_type),
                idempotency_key=request.idempotency_key or None,
                metadata=metadata,
            )
            session.commit()
            _record_grpc_status("RecordRecommendationEvent", "ok", started_at)
            return recommendation_pb2.RecordRecommendationEventResponse(
                interaction_id=str(response.interaction_id),
                duplicate=response.duplicate,
            )
        except ValueError as exc:
            if session is not None:
                session.rollback()
            _record_grpc_status(
                "RecordRecommendationEvent",
                "invalid_argument",
                started_at,
            )
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        except Exception:
            if session is not None:
                session.rollback()
            _record_grpc_status("RecordRecommendationEvent", "error", started_at)
            raise
        finally:
            if session is not None:
                session.close()

    def _resolve_external_user_id(self, context) -> str:
        try:
            return self._auth_resolver.resolve_external_user_id(
                metadata_to_dict(context.invocation_metadata()),
            )
        except AuthError as exc:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, str(exc))


def _recommendation_to_proto(item):
    message = recommendation_pb2.BeverageRecommendation(
        rank=item.rank,
        result_id=str(item.result_id),
        beverage_id=item.target_id,
        name_ko=item.name_ko,
        name_en=item.name_en or "",
        category=item.category,
        score=item.final_score,
        reason_codes=item.reason_codes,
        explanation=item.explanation,
    )
    metadata = {
        "style": item.style or "",
        "similarity_score": item.similarity_score,
        "score_breakdown": item.score_breakdown,
        "source": item.source_metadata,
    }
    json_format.ParseDict(metadata, message.metadata)
    return message


def _venue_recommendation_to_proto(item):
    message = recommendation_pb2.VenueRecommendation(
        rank=item.rank,
        result_id=str(item.result_id),
        place_id=item.place_id,
        name=item.name,
        place_type=item.place_type,
        address=item.address or "",
        option_type=_venue_option_type_to_proto(item.option_type),
        distance_m=item.distance_m,
        availability_status=_venue_availability_to_proto(item.availability_status),
        freshness_status=_venue_freshness_to_proto(item.freshness_status),
        score=item.final_score,
        reason_codes=item.reason_codes,
        explanation=item.explanation,
    )
    if item.price_krw is not None:
        message.price_krw = item.price_krw
    metadata = {
        "score_breakdown": item.score_breakdown,
        "source": item.source_metadata,
    }
    json_format.ParseDict(metadata, message.metadata)
    return message


def _profile_status_to_proto(status: str) -> int:
    return {
        "missing": recommendation_pb2.PROFILE_STATUS_MISSING,
        "pending_generation": recommendation_pb2.PROFILE_STATUS_PENDING_GENERATION,
        "active": recommendation_pb2.PROFILE_STATUS_ACTIVE,
        "stale": recommendation_pb2.PROFILE_STATUS_STALE,
        "failed_generation": recommendation_pb2.PROFILE_STATUS_FAILED_GENERATION,
    }.get(status, recommendation_pb2.PROFILE_STATUS_UNSPECIFIED)


def _budget_mode_from_proto(value: int) -> str:
    if value == recommendation_pb2.BUDGET_MODE_STRICT:
        return "strict"
    return "soft"


def _event_type_from_proto(value: int) -> str:
    event_type = {
        recommendation_pb2.RECOMMENDATION_EVENT_TYPE_IMPRESSION: "impression",
        recommendation_pb2.RECOMMENDATION_EVENT_TYPE_CLICK: "click",
        recommendation_pb2.RECOMMENDATION_EVENT_TYPE_SAVE: "save",
        recommendation_pb2.RECOMMENDATION_EVENT_TYPE_DISMISS: "dismiss",
        recommendation_pb2.RECOMMENDATION_EVENT_TYPE_DETAIL_VIEW: "detail_view",
    }.get(value)
    if event_type is None:
        raise ValueError("event_type is required")
    return event_type


def _venue_option_type_to_proto(value: str) -> int:
    return {
        "nearest_reasonable": recommendation_pb2.VENUE_OPTION_TYPE_NEAREST_REASONABLE,
        "best_price": recommendation_pb2.VENUE_OPTION_TYPE_BEST_PRICE,
        "balanced_best": recommendation_pb2.VENUE_OPTION_TYPE_BALANCED_BEST,
    }.get(value, recommendation_pb2.VENUE_OPTION_TYPE_UNSPECIFIED)


def _venue_availability_to_proto(value: str) -> int:
    return {
        "available": recommendation_pb2.VENUE_AVAILABILITY_STATUS_AVAILABLE,
        "likely_available": (
            recommendation_pb2.VENUE_AVAILABILITY_STATUS_LIKELY_AVAILABLE
        ),
        "unknown": recommendation_pb2.VENUE_AVAILABILITY_STATUS_UNKNOWN,
        "unavailable": recommendation_pb2.VENUE_AVAILABILITY_STATUS_UNAVAILABLE,
    }.get(value, recommendation_pb2.VENUE_AVAILABILITY_STATUS_UNSPECIFIED)


def _venue_freshness_to_proto(value: str) -> int:
    return {
        "fresh": recommendation_pb2.VENUE_FRESHNESS_STATUS_FRESH,
        "stale": recommendation_pb2.VENUE_FRESHNESS_STATUS_STALE,
        "expired": recommendation_pb2.VENUE_FRESHNESS_STATUS_EXPIRED,
    }.get(value, recommendation_pb2.VENUE_FRESHNESS_STATUS_UNSPECIFIED)


def _record_grpc_status(method: str, status: str, started_at: float) -> None:
    runtime_metrics.record(
        f"grpc_{method}",
        latency_ms=round((perf_counter() - started_at) * 1000, 3),
        error=status != "ok",
        status=status,
    )
