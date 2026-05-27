import logging
from concurrent import futures

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.grpc.gen import recommendation_pb2_grpc
from app.grpc.recommendation_service import RecommendationGrpcServicer
from app.services.auth import create_auth_context_resolver

logger = logging.getLogger(__name__)


def create_grpc_server(
    settings: Settings | None = None,
    *,
    bind_port: bool = True,
) -> grpc.Server:
    resolved_settings = settings or get_settings()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    health_servicer = health.HealthServicer()
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set(
        resolved_settings.grpc_health_service_name,
        health_pb2.HealthCheckResponse.SERVING,
    )
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    recommendation_pb2_grpc.add_RecommendationServiceServicer_to_server(
        RecommendationGrpcServicer(
            SessionLocal,
            create_auth_context_resolver(resolved_settings),
        ),
        server,
    )

    if bind_port:
        listen_addr = f"{resolved_settings.grpc_host}:{resolved_settings.grpc_port}"
        server.add_insecure_port(listen_addr)
    return server


def serve(settings: Settings | None = None) -> None:
    resolved_settings = settings or get_settings()
    server = create_grpc_server(resolved_settings)
    listen_addr = f"{resolved_settings.grpc_host}:{resolved_settings.grpc_port}"

    server.start()
    logger.info("gRPC server started on %s", listen_addr)
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(grace=5)
        raise
