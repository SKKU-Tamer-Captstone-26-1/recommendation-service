# ruff: noqa
"""Dynamic protobuf definitions for survey/v1/survey.proto."""

from google.protobuf import descriptor_pb2 as _descriptor_pb2
from google.protobuf import descriptor_pool as _descriptor_pool
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


_file = _descriptor_pb2.FileDescriptorProto()
_file.name = "survey/v1/survey.proto"
_file.package = "ontheblock.survey.v1"
_file.syntax = "proto3"
_file.dependency.append("google/protobuf/timestamp.proto")
_file.options.java_package = "com.ontheblock.survey.v1"
_file.options.java_multiple_files = True
_file.options.go_package = "github.com/ontheblock/infra/proto/survey/v1;surveyv1"

_get_result_request = _message(_file, "GetSurveyResultRequest")
_add_field(
    _get_result_request,
    "survey_id",
    1,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
)

_get_result_by_user_request = _message(_file, "GetSurveyResultByUserRequest")
_add_field(
    _get_result_by_user_request,
    "user_id",
    1,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
)

_result_response = _message(_file, "GetSurveyResultResponse")
_add_field(
    _result_response,
    "result",
    1,
    _descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
    type_name=".ontheblock.survey.v1.SurveyResult",
)

_survey_result = _message(_file, "SurveyResult")
_add_field(
    _survey_result,
    "survey_id",
    1,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
)
_add_field(
    _survey_result,
    "user_id",
    2,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
)
_add_field(
    _survey_result,
    "level",
    3,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
)
_add_field(
    _survey_result,
    "categories",
    4,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    label=_descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
)
_add_field(
    _survey_result,
    "whiskey",
    5,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    label=_descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
)
_add_field(
    _survey_result,
    "wine",
    6,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    label=_descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
)
_add_field(
    _survey_result,
    "cocktail",
    7,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    label=_descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
)
_add_field(
    _survey_result,
    "beer",
    8,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    label=_descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
)
_add_field(
    _survey_result,
    "flavor_keywords",
    9,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    label=_descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
)
_add_field(
    _survey_result,
    "budget",
    10,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
)
_add_field(
    _survey_result,
    "submitted_at",
    11,
    _descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
    type_name=".google.protobuf.Timestamp",
)

DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    _file.SerializeToString()
)
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, "survey_pb2", globals())

_timestamp_pb2.DESCRIPTOR
