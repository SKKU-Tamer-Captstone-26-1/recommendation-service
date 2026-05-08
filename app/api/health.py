from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import check_database, get_db
from app.infrastructure.qdrant.client import check_qdrant
from app.schemas.health import DependencyStatus, HealthResponse, ServiceStatusResponse

router = APIRouter(tags=["health"])

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_db)]


@router.get("/health/live", response_model=HealthResponse)
def live(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.app_env,
        version=settings.app_version,
        dependencies=[],
    )


@router.get("/health/ready", response_model=HealthResponse)
def ready(
    db: SessionDep,
    settings: SettingsDep,
) -> HealthResponse:
    dependencies: list[DependencyStatus] = []

    try:
        check_database(db)
        dependencies.append(
            DependencyStatus(name="postgresql", status="ok", required=True),
        )
    except Exception as exc:  # noqa: BLE001
        dependencies.append(
            DependencyStatus(
                name="postgresql",
                status="error",
                required=True,
                detail=str(exc),
            ),
        )

    try:
        check_qdrant(settings)
        dependencies.append(
            DependencyStatus(
                name="qdrant",
                status="ok",
                required=settings.qdrant_indexing_enabled,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        dependencies.append(
            DependencyStatus(
                name="qdrant",
                status="error",
                required=settings.qdrant_indexing_enabled,
                detail=str(exc),
            ),
        )

    required_dependencies = [
        dependency for dependency in dependencies if dependency.required
    ]
    status = (
        "ready"
        if all(dependency.status == "ok" for dependency in required_dependencies)
        else "not_ready"
    )

    return HealthResponse(
        status=status,
        service=settings.app_name,
        environment=settings.app_env,
        version=settings.app_version,
        dependencies=dependencies,
    )


@router.get("/v1/status", response_model=ServiceStatusResponse)
def service_status(settings: SettingsDep) -> ServiceStatusResponse:
    return ServiceStatusResponse(
        service=settings.app_name,
        environment=settings.app_env,
        version=settings.app_version,
        active_vector_schema=settings.active_vector_schema,
        active_survey_mapper=settings.active_survey_mapper,
        active_scoring_config=settings.active_scoring_config,
        qdrant_indexing_enabled=settings.qdrant_indexing_enabled,
        profile_regeneration_enabled=settings.profile_regeneration_enabled,
    )
