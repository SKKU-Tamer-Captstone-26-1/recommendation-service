from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.operations import OperationalMetricsResponse
from app.services.operational_metrics import OperationalMetricsService

router = APIRouter(tags=["operations"])

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_db)]


@router.get("/v1/operations/metrics", response_model=OperationalMetricsResponse)
def operational_metrics(
    db: SessionDep,
    settings: SettingsDep,
) -> OperationalMetricsResponse:
    snapshot = OperationalMetricsService.from_session(db).snapshot()
    return OperationalMetricsResponse(
        service=settings.app_name,
        environment=settings.app_env,
        generated_at=snapshot.generated_at,
        metrics=snapshot.metrics,
    )
