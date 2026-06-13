from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "local"
    app_name: str = "recommendation-service"
    app_version: str = "0.1.0"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    enable_openapi_docs: bool = True

    grpc_host: str = "0.0.0.0"
    grpc_port: int = 50051
    grpc_health_service_name: str = "ontheblock.recommendation.v1.RecommendationService"

    database_url: str = Field(
        default=(
            "postgresql+psycopg://recommendation_user:change_me_local_only"
            "@localhost:5432/recommendation_service"
        )
    )
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_echo: bool = False

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_timeout_seconds: float = 5.0
    qdrant_beverage_collection: str = "beverage_vectors_v1"
    qdrant_profile_collection: str = "profile_vectors_v1"
    qdrant_venue_collection: str = "venue_vectors_v1"
    qdrant_menu_item_collection: str = "menu_item_vectors_v1"

    auth_service_url: str = "http://localhost:8081"
    auth_service_grpc_addr: str = "localhost:50052"
    auth_service_grpc_tls: bool | None = None
    auth_token_validation_mode: str = "grpc"
    auth_request_timeout_seconds: float = 5.0
    auth_jwks_url: str = "http://localhost:8081/.well-known/jwks.json"
    jwt_issuer: str = "on-the-block-auth"
    jwt_audience: str = "recommendation-service"

    survey_service_url: str = "http://localhost:8082"
    survey_service_grpc_addr: str = "localhost:50053"
    survey_events_path: str = "/internal/v1/recommendation/survey-events"
    survey_response_path_template: str = (
        "/internal/v1/recommendation/survey-responses/{survey_response_id}"
    )
    survey_request_timeout_seconds: float = 10.0
    survey_events_poll_interval_seconds: int = 10
    survey_events_page_size: int = 100

    map_service_url: str = "http://localhost:8083"
    map_service_grpc_addr: str = "localhost:50054"
    map_snapshot_events_path: str = "/internal/v1/recommendation/map-snapshot-events"
    map_snapshot_events_page_size: int = 100
    map_snapshot_request_timeout_seconds: float = 10.0
    map_route_distance_enabled: bool = False
    map_route_distance_path: str = "/internal/v1/recommendation/route-distance"
    map_route_distance_timeout_seconds: float = 3.0
    map_route_distance_fallback_enabled: bool = True
    map_service_serverless_audience: str | None = None
    map_service_serverless_token_timeout_seconds: float = 1.0

    sync_worker_enabled: bool = True
    sync_max_attempts: int = 5
    sync_retry_base_seconds: int = 30
    profile_regeneration_enabled: bool = True
    qdrant_indexing_enabled: bool = True

    default_recommendation_limit: int = 20
    default_venue_radius_meters: int = 3000
    active_vector_schema: str = "taste_v1"
    active_survey_mapper: str = "survey_mapper_v1_1"
    active_scoring_config: str = "scoring_v3"
    beverage_image_cdn_base_url: str | None = None

    request_id_header: str = "X-Request-ID"
    structured_logs: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
