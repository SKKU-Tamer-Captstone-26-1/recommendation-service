# ruff: noqa
"""gRPC bindings for auth/v1/auth.proto."""

from app.grpc.gen import auth_pb2 as auth__pb2


class AuthServiceStub:
    def __init__(self, channel):
        self.ValidateToken = channel.unary_unary(
            "/ontheblock.auth.v1.AuthService/ValidateToken",
            request_serializer=auth__pb2.ValidateTokenRequest.SerializeToString,
            response_deserializer=auth__pb2.ValidateTokenResponse.FromString,
        )
        self.GetPublicKeys = channel.unary_unary(
            "/ontheblock.auth.v1.AuthService/GetPublicKeys",
            request_serializer=auth__pb2.GetPublicKeysRequest.SerializeToString,
            response_deserializer=auth__pb2.GetPublicKeysResponse.FromString,
        )
