# ruff: noqa
"""Dynamic protobuf definitions for auth/v1/auth.proto."""

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
_file.name = "auth/v1/auth.proto"
_file.package = "ontheblock.auth.v1"
_file.syntax = "proto3"
_file.dependency.append("google/protobuf/timestamp.proto")
_file.options.java_package = "com.ontheblock.auth.v1"
_file.options.java_multiple_files = True
_file.options.go_package = "github.com/ontheblock/infra/proto/auth/v1;authv1"

_role = _file.enum_type.add()
_role.name = "Role"
for number, name in (
    (0, "ROLE_UNSPECIFIED"),
    (1, "ROLE_NORMAL"),
    (2, "ROLE_ADMIN"),
    (3, "ROLE_BAR"),
    (4, "ROLE_REQUE"),
):
    value = _role.value.add()
    value.name = name
    value.number = number

_validate_token_request = _message(_file, "ValidateTokenRequest")
_add_field(
    _validate_token_request,
    "access_token",
    1,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
)

_validate_token_response = _message(_file, "ValidateTokenResponse")
_add_field(
    _validate_token_response,
    "valid",
    1,
    _descriptor_pb2.FieldDescriptorProto.TYPE_BOOL,
)
_add_field(
    _validate_token_response,
    "user_id",
    2,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
)
_add_field(
    _validate_token_response,
    "email",
    3,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
)
_add_field(
    _validate_token_response,
    "role",
    4,
    _descriptor_pb2.FieldDescriptorProto.TYPE_ENUM,
    type_name=".ontheblock.auth.v1.Role",
)
_add_field(
    _validate_token_response,
    "expires_at",
    5,
    _descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
    type_name=".google.protobuf.Timestamp",
)
_add_field(
    _validate_token_response,
    "reason",
    6,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
)
_add_field(
    _validate_token_response,
    "nickname",
    7,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
)

_get_public_keys_request = _message(_file, "GetPublicKeysRequest")

_public_key_entry = _message(_file, "PublicKeyEntry")
_add_field(
    _public_key_entry,
    "kid",
    1,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
)
_add_field(
    _public_key_entry,
    "public_key_pem",
    2,
    _descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
)
_add_field(
    _public_key_entry,
    "is_current",
    3,
    _descriptor_pb2.FieldDescriptorProto.TYPE_BOOL,
)

_get_public_keys_response = _message(_file, "GetPublicKeysResponse")
_add_field(
    _get_public_keys_response,
    "keys",
    1,
    _descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
    label=_descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
    type_name=".ontheblock.auth.v1.PublicKeyEntry",
)

DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(_file.SerializeToString())
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, "auth_pb2", globals())

_timestamp_pb2.DESCRIPTOR
