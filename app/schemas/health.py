from pydantic import BaseModel, Field


class DependencyStatus(BaseModel):
    name: str
    status: str
    required: bool
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    version: str
    dependencies: list[DependencyStatus] = Field(default_factory=list)


class ServiceStatusResponse(BaseModel):
    service: str
    environment: str
    version: str
    active_vector_schema: str
    active_survey_mapper: str
    active_scoring_config: str
    qdrant_indexing_enabled: bool
    profile_regeneration_enabled: bool
