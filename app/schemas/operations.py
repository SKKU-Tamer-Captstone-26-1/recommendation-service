from datetime import datetime

from pydantic import BaseModel, Field


class OperationalMetricsResponse(BaseModel):
    service: str
    environment: str
    generated_at: datetime
    metrics: dict[str, int | float | None] = Field(default_factory=dict)
