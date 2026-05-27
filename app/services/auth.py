from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import grpc

from app.core.config import Settings
from app.grpc.gen import auth_pb2, auth_pb2_grpc


class AuthError(ValueError):
    """Raised when authenticated caller identity cannot be resolved."""


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    external_user_id: str


class AuthContextResolver(Protocol):
    def resolve_external_user_id(self, metadata: dict[str, str]) -> str: ...


class StaticAuthContextResolver:
    """Test/local resolver for trusted in-process calls."""

    def __init__(self, external_user_id: str) -> None:
        self._external_user_id = external_user_id

    def resolve_external_user_id(self, metadata: dict[str, str]) -> str:
        return self._external_user_id


class JwtAuthContextResolver:
    """Resolve caller identity from auth-service issued JWTs."""

    def __init__(
        self,
        settings: Settings,
        *,
        jwks_ttl_seconds: int = 300,
    ) -> None:
        self._settings = settings
        self._jwks_ttl_seconds = jwks_ttl_seconds
        self._jwks_client: object | None = None

    def resolve_external_user_id(self, metadata: dict[str, str]) -> str:
        token = _bearer_token(metadata)
        payload = self._decode(token)
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise AuthError("JWT is missing subject")
        return subject

    def _decode(self, token: str) -> dict[str, object]:
        jwt = _jwt_module()
        if self._jwks_client is None:
            self._jwks_client = jwt.PyJWKClient(
                self._settings.auth_jwks_url,
                cache_jwk_set=True,
                lifespan=self._jwks_ttl_seconds,
            )
        jwks_client = self._jwks_client
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=self._settings.jwt_audience,
            issuer=self._settings.jwt_issuer,
        )
        if not isinstance(payload, dict):
            raise AuthError("JWT payload is invalid")
        return payload


class GrpcAuthContextResolver:
    """Resolve caller identity through auth-service token validation RPC."""

    def __init__(
        self,
        settings: Settings,
        *,
        stub: auth_pb2_grpc.AuthServiceStub | None = None,
    ) -> None:
        self._settings = settings
        self._stub = stub
        self._channel: grpc.Channel | None = None

    def resolve_external_user_id(self, metadata: dict[str, str]) -> str:
        token = _bearer_token(metadata)
        try:
            response = self._get_stub().ValidateToken(
                auth_pb2.ValidateTokenRequest(access_token=token),
                timeout=self._settings.auth_request_timeout_seconds,
            )
        except grpc.RpcError as exc:
            code = exc.code().name if exc.code() is not None else "UNKNOWN"
            raise AuthError(
                f"auth-service token validation RPC failed: {code}"
            ) from exc

        if not response.valid:
            reason = response.reason or "token invalid"
            raise AuthError(f"auth-service rejected bearer token: {reason}")
        if not response.user_id:
            raise AuthError("auth-service token validation returned no user_id")
        return response.user_id

    def _get_stub(self):
        if self._stub is not None:
            return self._stub
        if self._channel is None:
            self._channel = _auth_grpc_channel(self._settings)
        self._stub = auth_pb2_grpc.AuthServiceStub(self._channel)
        return self._stub


def create_auth_context_resolver(settings: Settings) -> AuthContextResolver:
    mode = settings.auth_token_validation_mode.lower()
    if mode == "grpc":
        return GrpcAuthContextResolver(settings)
    if mode in {"jwks", "jwt"}:
        return JwtAuthContextResolver(settings)
    raise ValueError(f"unsupported auth token validation mode: {mode}")


def metadata_to_dict(metadata: object) -> dict[str, str]:
    return {
        key.lower(): value
        for key, value in dict(metadata or {}).items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _bearer_token(metadata: dict[str, str]) -> str:
    authorization = metadata.get("authorization")
    if not authorization:
        raise AuthError("authorization metadata is missing")
    prefix = "bearer "
    if not authorization.lower().startswith(prefix):
        raise AuthError("authorization metadata must use bearer token")
    token = authorization[len(prefix) :].strip()
    if not token:
        raise AuthError("bearer token is empty")
    return token


def _jwt_module():
    try:
        import jwt  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on installed extras
        raise AuthError("PyJWT[crypto] is required for JWT verification") from exc
    return jwt


def _auth_grpc_channel(settings: Settings) -> grpc.Channel:
    use_tls = (
        settings.auth_service_grpc_tls
        if settings.auth_service_grpc_tls is not None
        else settings.auth_service_grpc_addr.endswith(":443")
    )
    if use_tls:
        return grpc.secure_channel(
            settings.auth_service_grpc_addr,
            grpc.ssl_channel_credentials(),
        )
    return grpc.insecure_channel(settings.auth_service_grpc_addr)
