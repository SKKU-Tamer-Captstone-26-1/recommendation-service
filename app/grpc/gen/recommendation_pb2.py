# ruff: noqa
"""Dynamic protobuf definitions for recommendation/v1/recommendation.proto."""

from google.protobuf import descriptor_pb2 as _descriptor_pb2
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import builder as _builder


def _add_field(message, name, number, field_type, *, label=None, type_name=None):
    field = message.field.add()
    field.name = name
    field.number = number
    field.label = label or _descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    field.type = field_type
    if type_name:
        field.type_name = type_name


def _message(file_proto, name):
    message = file_proto.message_type.add()
    message.name = name
    return message


def _enum(file_proto, name, values):
    enum = file_proto.enum_type.add()
    enum.name = name
    for index, value_name in enumerate(values):
        value = enum.value.add()
        value.name = value_name
        value.number = index
    return enum


_file = _descriptor_pb2.FileDescriptorProto()
_file.name = "recommendation/v1/recommendation.proto"
_file.package = "ontheblock.recommendation.v1"
_file.syntax = "proto3"
_file.dependency.append("google/protobuf/struct.proto")
_file.dependency.append("google/protobuf/timestamp.proto")
_file.options.java_package = "com.ontheblock.recommendation.v1"
_file.options.java_multiple_files = True
_file.options.go_package = (
    "github.com/ontheblock/infra/proto/recommendation/v1;recommendationv1"
)

_enum(
    _file,
    "ProfileStatus",
    (
        "PROFILE_STATUS_UNSPECIFIED",
        "PROFILE_STATUS_MISSING",
        "PROFILE_STATUS_PENDING_GENERATION",
        "PROFILE_STATUS_ACTIVE",
        "PROFILE_STATUS_STALE",
        "PROFILE_STATUS_FAILED_GENERATION",
    ),
)
_enum(
    _file,
    "BudgetMode",
    (
        "BUDGET_MODE_UNSPECIFIED",
        "BUDGET_MODE_SOFT",
        "BUDGET_MODE_STRICT",
    ),
)
_enum(
    _file,
    "RecommendationEventType",
    (
        "RECOMMENDATION_EVENT_TYPE_UNSPECIFIED",
        "RECOMMENDATION_EVENT_TYPE_IMPRESSION",
        "RECOMMENDATION_EVENT_TYPE_CLICK",
        "RECOMMENDATION_EVENT_TYPE_SAVE",
        "RECOMMENDATION_EVENT_TYPE_DISMISS",
        "RECOMMENDATION_EVENT_TYPE_DETAIL_VIEW",
    ),
)

_message(_file, "GetProfileStatusRequest")

_status_response = _message(_file, "GetProfileStatusResponse")
_add_field(
    _status_response,
    "status",
    1,
    _descriptor_pb2.FieldDescriptorProto.TYPE_ENUM,
    type_name=".ontheblock.recommendation.v1.ProfileStatus",
)
_add_field(
    _status_response,
    "profile_revision",
    2,
    _descriptor_pb2.FieldDescriptorProto.TYPE_INT32,
)
_add_field(
    _status_response,
    "survey_response_id",
    3,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
)
_add_field(
    _status_response,
    "generated_at",
    4,
    _descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
    type_name=".google.protobuf.Timestamp",
)
_add_field(
    _status_response,
    "stale_reason",
    5,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
)

_bev_request = _message(_file, "GetBeverageRecommendationsRequest")
_add_field(_bev_request, "category", 1, _descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
_add_field(_bev_request, "limit", 2, _descriptor_pb2.FieldDescriptorProto.TYPE_INT32)
_add_field(
    _bev_request,
    "budget_mode",
    3,
    _descriptor_pb2.FieldDescriptorProto.TYPE_ENUM,
    type_name=".ontheblock.recommendation.v1.BudgetMode",
)

_bev_result = _message(_file, "BeverageRecommendation")
_add_field(_bev_result, "rank", 1, _descriptor_pb2.FieldDescriptorProto.TYPE_INT32)
_add_field(_bev_result, "result_id", 2, _descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
_add_field(_bev_result, "beverage_id", 3, _descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
_add_field(_bev_result, "name_ko", 4, _descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
_add_field(_bev_result, "name_en", 5, _descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
_add_field(_bev_result, "category", 6, _descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
_add_field(_bev_result, "score", 7, _descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE)
_add_field(
    _bev_result,
    "reason_codes",
    8,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    label=_descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
)
_add_field(_bev_result, "explanation", 9, _descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
_add_field(
    _bev_result,
    "metadata",
    10,
    _descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
    type_name=".google.protobuf.Struct",
)

_bev_response = _message(_file, "GetBeverageRecommendationsResponse")
_add_field(_bev_response, "request_id", 1, _descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
_add_field(
    _bev_response,
    "profile_status",
    2,
    _descriptor_pb2.FieldDescriptorProto.TYPE_ENUM,
    type_name=".ontheblock.recommendation.v1.ProfileStatus",
)
_add_field(
    _bev_response,
    "profile_revision",
    3,
    _descriptor_pb2.FieldDescriptorProto.TYPE_INT32,
)
_add_field(
    _bev_response,
    "recommendations",
    4,
    _descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
    label=_descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
    type_name=".ontheblock.recommendation.v1.BeverageRecommendation",
)

_event_request = _message(_file, "RecordRecommendationEventRequest")
_add_field(_event_request, "request_id", 1, _descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
_add_field(_event_request, "result_id", 2, _descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
_add_field(
    _event_request,
    "event_type",
    3,
    _descriptor_pb2.FieldDescriptorProto.TYPE_ENUM,
    type_name=".ontheblock.recommendation.v1.RecommendationEventType",
)
_add_field(
    _event_request,
    "idempotency_key",
    4,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
)
_add_field(
    _event_request,
    "metadata",
    5,
    _descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
    type_name=".google.protobuf.Struct",
)

_event_response = _message(_file, "RecordRecommendationEventResponse")
_add_field(
    _event_response,
    "interaction_id",
    1,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
)
_add_field(_event_response, "duplicate", 2, _descriptor_pb2.FieldDescriptorProto.TYPE_BOOL)

DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(_file.SerializeToString())
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(
    DESCRIPTOR,
    "app.grpc.gen.recommendation_pb2",
    globals(),
)
