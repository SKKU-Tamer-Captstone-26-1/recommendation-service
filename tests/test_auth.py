import pytest

from app.core.config import Settings
from app.grpc.gen import auth_pb2
from app.services.auth import (
    AuthError,
    GrpcAuthContextResolver,
    JwtAuthContextResolver,
    create_auth_context_resolver,
    metadata_to_dict,
)


def test_metadata_to_dict_normalizes_grpc_metadata() -> None:
    metadata = (
        ("Authorization", "Bearer token"),
        ("x-request-id", "req_123"),
        ("ignored", 123),
    )

    assert metadata_to_dict(metadata) == {
        "authorization": "Bearer token",
        "x-request-id": "req_123",
    }


def test_jwt_resolver_requires_bearer_authorization_metadata() -> None:
    resolver = JwtAuthContextResolver(Settings())

    with pytest.raises(AuthError, match="authorization metadata is missing"):
        resolver.resolve_external_user_id({})

    with pytest.raises(AuthError, match="must use bearer token"):
        resolver.resolve_external_user_id({"authorization": "Basic token"})

    with pytest.raises(AuthError, match="bearer token is empty"):
        resolver.resolve_external_user_id({"authorization": "Bearer "})


def test_grpc_auth_resolver_validates_token_with_auth_service() -> None:
    stub = _FakeAuthStub(
        auth_pb2.ValidateTokenResponse(valid=True, user_id="usr_123"),
    )
    resolver = GrpcAuthContextResolver(Settings(), stub=stub)

    external_user_id = resolver.resolve_external_user_id(
        {"authorization": "Bearer access-token"},
    )

    assert external_user_id == "usr_123"
    assert stub.requests == ["access-token"]


def test_grpc_auth_resolver_rejects_invalid_token() -> None:
    resolver = GrpcAuthContextResolver(
        Settings(),
        stub=_FakeAuthStub(
            auth_pb2.ValidateTokenResponse(valid=False, reason="TOKEN_INVALID"),
        ),
    )

    with pytest.raises(AuthError, match="TOKEN_INVALID"):
        resolver.resolve_external_user_id({"authorization": "Bearer bad-token"})


def test_create_auth_context_resolver_uses_configured_mode() -> None:
    assert isinstance(
        create_auth_context_resolver(Settings(auth_token_validation_mode="grpc")),
        GrpcAuthContextResolver,
    )
    assert isinstance(
        create_auth_context_resolver(Settings(auth_token_validation_mode="jwks")),
        JwtAuthContextResolver,
    )


class _FakeAuthStub:
    def __init__(self, response: auth_pb2.ValidateTokenResponse) -> None:
        self._response = response
        self.requests: list[str] = []

    def ValidateToken(self, request, *, timeout):
        self.requests.append(request.access_token)
        assert timeout == Settings().auth_request_timeout_seconds
        return self._response
