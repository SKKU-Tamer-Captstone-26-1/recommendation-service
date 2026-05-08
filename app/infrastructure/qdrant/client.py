from qdrant_client import QdrantClient

from app.core.config import Settings, get_settings


def create_qdrant_client(settings: Settings | None = None) -> QdrantClient:
    resolved_settings = settings or get_settings()
    return QdrantClient(
        url=resolved_settings.qdrant_url,
        api_key=resolved_settings.qdrant_api_key or None,
        timeout=resolved_settings.qdrant_timeout_seconds,
    )


def check_qdrant(settings: Settings | None = None) -> bool:
    resolved_settings = settings or get_settings()
    if not resolved_settings.qdrant_indexing_enabled:
        return True

    client = create_qdrant_client(resolved_settings)
    client.get_collections()
    return True

