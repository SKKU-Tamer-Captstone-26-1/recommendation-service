from dataclasses import dataclass

from app.core.config import Settings
from app.models.versioning import MapperVersion, ScoringConfig, VectorSchemaVersion
from app.repositories.versioning import VersioningRepository

REQUIRED_SCORING_TARGET_TYPES = ("beverage", "venue")


@dataclass(frozen=True)
class FoundationRegistryState:
    vector_schema: VectorSchemaVersion | None
    mapper_version: MapperVersion | None
    scoring_configs: tuple[ScoringConfig, ...]
    missing_keys: tuple[str, ...]

    @property
    def is_ready(self) -> bool:
        return not self.missing_keys


class FoundationService:
    """Coordinates foundation metadata reads without owning business logic."""

    def __init__(
        self,
        repository: VersioningRepository,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._settings = settings

    def load_active_registry_state(self) -> FoundationRegistryState:
        vector_schema = self._repository.get_active_vector_schema(
            self._settings.active_vector_schema,
        )
        mapper_version = self._repository.get_active_mapper_version(
            self._settings.active_survey_mapper,
        )
        scoring_configs = self._repository.list_active_scoring_configs(
            self._settings.active_scoring_config,
        )

        missing_keys: list[str] = []
        if vector_schema is None:
            missing_keys.append(f"vector_schema:{self._settings.active_vector_schema}")
        if mapper_version is None:
            missing_keys.append(f"mapper:{self._settings.active_survey_mapper}")

        scoring_targets = {config.target_type for config in scoring_configs}
        for target_type in REQUIRED_SCORING_TARGET_TYPES:
            if target_type not in scoring_targets:
                missing_keys.append(
                    f"scoring:{self._settings.active_scoring_config}:{target_type}",
                )

        return FoundationRegistryState(
            vector_schema=vector_schema,
            mapper_version=mapper_version,
            scoring_configs=scoring_configs,
            missing_keys=tuple(missing_keys),
        )
