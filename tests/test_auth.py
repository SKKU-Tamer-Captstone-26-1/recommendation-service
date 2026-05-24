import pytest

from app.core.config import Settings
from app.services.auth import AuthError, JwtAuthContextResolver, metadata_to_dict


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
