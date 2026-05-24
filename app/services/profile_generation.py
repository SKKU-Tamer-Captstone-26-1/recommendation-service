from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.vector_schema import TASTE_V1_DIMENSIONS, TASTE_V1_NAME
from app.models.enums import ProfileStatus, VectorOwnerType
from app.models.profile import (
    SurveySourceSnapshot,
    TasteProfileRevision,
    UserProfileState,
)
from app.models.vector import RecommendationVector
from app.models.versioning import MapperVersion, ScoringConfig, VectorSchemaVersion

KEYWORD_DIMENSION_WEIGHTS: dict[str, dict[str, float]] = {
    "vanilla_caramel": {"sweet": 0.85, "woody": 0.55},
    "citrus_berry": {"fruity": 0.8, "acidity": 0.65},
    "dried_fruit_chocolate": {"dried_fruit": 0.75, "roasted": 0.55, "sweet": 0.4},
    "oak_woody": {"woody": 0.8, "spicy": 0.45, "tannin": 0.45},
    "smoky_peat": {"smoky": 0.85, "alcohol_intensity": 0.5},
    "nutty": {"nutty": 0.8, "body": 0.45},
    "floral": {"floral": 0.8},
    "spicy": {"spicy": 0.8, "woody": 0.35},
    "herbal_mint": {"herbal": 0.8, "bitterness": 0.4},
    "sour": {"acidity": 0.75, "fruity": 0.35},
    "spirit_forward": {"alcohol_intensity": 0.75, "body": 0.45},
}

CATEGORY_BASE_WEIGHTS: dict[str, dict[str, float]] = {
    "whiskey": {"woody": 0.35, "body": 0.3, "alcohol_intensity": 0.3},
    "wine": {"fruity": 0.35, "acidity": 0.35, "tannin": 0.25},
    "beer": {"carbonation": 0.35, "bitterness": 0.3, "body": 0.25},
    "cocktail": {"sweet": 0.25, "acidity": 0.3, "alcohol_intensity": 0.25},
    "gin": {"herbal": 0.45, "floral": 0.25, "bitterness": 0.25},
    "rum": {"sweet": 0.35, "body": 0.3, "spicy": 0.25},
    "vodka": {"alcohol_intensity": 0.35, "body": 0.2},
    "liqueur": {"sweet": 0.45, "body": 0.25},
    "brandy_cognac": {"dried_fruit": 0.35, "woody": 0.35, "body": 0.3},
    "sake_shochu": {"body": 0.25, "fruity": 0.25, "alcohol_intensity": 0.25},
    "tequila_mezcal": {"herbal": 0.25, "spicy": 0.25, "alcohol_intensity": 0.35},
    "traditional_korean_alcohol": {"sweet": 0.3, "body": 0.25, "acidity": 0.25},
}


@dataclass(frozen=True)
class SurveyProfileInput:
    survey_response_id: str
    external_user_id: str
    survey_version: str
    response_revision: int
    completed_at: datetime
    answers: dict[str, Any]


@dataclass(frozen=True)
class GeneratedProfile:
    taste_vector: list[float]
    taste_vector_json: dict[str, float]
    confidence_json: dict[str, float]
    preferred_categories: list[str]
    preferred_keywords: list[str]
    budget_range: str | None
    experience_level: str | None
    source_snapshot_hash: str
    redacted_snapshot_json: dict[str, Any]


class SurveyMapperV1:
    """Pure deterministic mapper from survey DTO to taste_v1 profile data."""

    def map(self, survey_input: SurveyProfileInput) -> GeneratedProfile:
        answers = survey_input.answers
        categories = _string_list(answers.get("categories"))
        keywords = _string_list(answers.get("global_keywords"))
        experience_level = _optional_string(answers.get("experience_level"))
        budget_range = _optional_string(answers.get("budget_range"))
        category_traits = answers.get("category_traits")
        if not isinstance(category_traits, dict):
            category_traits = {}

        scores = {dimension.name: 0.0 for dimension in TASTE_V1_DIMENSIONS}
        evidence_count = {dimension.name: 0 for dimension in TASTE_V1_DIMENSIONS}

        for category in categories:
            _add_weights(
                scores,
                evidence_count,
                CATEGORY_BASE_WEIGHTS.get(category, {}),
            )
        for keyword in keywords:
            _add_weights(
                scores,
                evidence_count,
                KEYWORD_DIMENSION_WEIGHTS.get(keyword, {}),
            )
        for traits in category_traits.values():
            for trait in _string_list(traits):
                _add_weights(
                    scores,
                    evidence_count,
                    KEYWORD_DIMENSION_WEIGHTS.get(trait, {}),
                )

        values = {
            dimension.name: min(1.0, round(scores[dimension.name], 4))
            for dimension in TASTE_V1_DIMENSIONS
        }
        confidence = {
            dimension.name: min(0.95, 0.35 + (0.15 * evidence_count[dimension.name]))
            for dimension in TASTE_V1_DIMENSIONS
        }
        vector = [values[dimension.name] for dimension in TASTE_V1_DIMENSIONS]
        snapshot = {
            "survey_response_id": survey_input.survey_response_id,
            "external_user_id": survey_input.external_user_id,
            "survey_version": survey_input.survey_version,
            "response_revision": survey_input.response_revision,
            "answers": {
                "experience_level": experience_level,
                "categories": categories,
                "category_traits": category_traits,
                "global_keywords": keywords,
                "budget_range": budget_range,
            },
        }
        return GeneratedProfile(
            taste_vector=vector,
            taste_vector_json=values,
            confidence_json=confidence,
            preferred_categories=categories,
            preferred_keywords=keywords,
            budget_range=budget_range,
            experience_level=experience_level,
            source_snapshot_hash=_hash_json(snapshot),
            redacted_snapshot_json=snapshot,
        )


class ProfileGenerationService:
    """Persists derived profiles without owning raw survey answers."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._mapper = SurveyMapperV1()

    def generate_from_survey_input(
        self,
        survey_input: SurveyProfileInput,
    ) -> TasteProfileRevision:
        mapper_version = _active_mapper(self._session)
        existing_profile = self._session.scalar(
            select(TasteProfileRevision).where(
                TasteProfileRevision.external_user_id
                == survey_input.external_user_id,
                TasteProfileRevision.survey_response_id
                == survey_input.survey_response_id,
                TasteProfileRevision.survey_response_revision
                == survey_input.response_revision,
                TasteProfileRevision.mapper_version_id == mapper_version.id,
            ),
        )
        if existing_profile is not None:
            state = self._session.get(
                UserProfileState,
                survey_input.external_user_id,
            )
            if state is None:
                state = UserProfileState(
                    external_user_id=survey_input.external_user_id,
                    status=ProfileStatus.ACTIVE.value,
                    last_survey_response_id=survey_input.survey_response_id,
                    last_survey_response_revision=survey_input.response_revision,
                )
                self._session.add(state)
            state.active_profile_revision_id = existing_profile.id
            state.status = ProfileStatus.ACTIVE.value
            state.last_survey_response_id = survey_input.survey_response_id
            state.last_survey_response_revision = survey_input.response_revision
            _ensure_profile_vector(self._session, existing_profile)
            self._session.flush()
            return existing_profile

        vector_schema = _active_vector_schema(self._session)
        scoring_config = _active_beverage_scoring(self._session)
        generated = self._mapper.map(survey_input)

        state = self._session.get(UserProfileState, survey_input.external_user_id)
        if state is None:
            state = UserProfileState(
                external_user_id=survey_input.external_user_id,
                status=ProfileStatus.PENDING_GENERATION.value,
                last_survey_response_id=survey_input.survey_response_id,
                last_survey_response_revision=survey_input.response_revision,
            )
            self._session.add(state)

        next_revision = (
            self._session.scalar(
                select(func.max(TasteProfileRevision.profile_revision)).where(
                    TasteProfileRevision.external_user_id
                    == survey_input.external_user_id,
                ),
            )
            or 0
        ) + 1
        profile = TasteProfileRevision(
            external_user_id=survey_input.external_user_id,
            profile_revision=next_revision,
            survey_response_id=survey_input.survey_response_id,
            survey_version=survey_input.survey_version,
            survey_response_revision=survey_input.response_revision,
            mapper_version_id=mapper_version.id,
            vector_schema_version_id=vector_schema.id,
            scoring_config_id=scoring_config.id,
            taste_vector=generated.taste_vector,
            taste_vector_json=generated.taste_vector_json,
            confidence_json=generated.confidence_json,
            preferred_categories=generated.preferred_categories,
            preferred_keywords=generated.preferred_keywords,
            budget_range=generated.budget_range,
            experience_level=generated.experience_level,
            status=ProfileStatus.ACTIVE.value,
            generated_at=datetime.now(UTC),
            generation_metadata_json={
                "mapper_version": mapper_version.version,
                "vector_schema": TASTE_V1_NAME,
                "source_snapshot_hash": generated.source_snapshot_hash,
            },
        )
        self._session.add(profile)
        self._session.flush()
        snapshot = SurveySourceSnapshot(
            profile_revision_id=profile.id,
            survey_response_id=survey_input.survey_response_id,
            survey_version=survey_input.survey_version,
            survey_response_revision=survey_input.response_revision,
            snapshot_hash=generated.source_snapshot_hash,
            snapshot_json=generated.redacted_snapshot_json,
            fetched_at=datetime.now(UTC),
            notes=(
                "Redacted survey generation evidence only; survey-service remains "
                "canonical."
            ),
        )
        self._session.add(snapshot)
        _ensure_profile_vector(self._session, profile, generated=generated)
        state.active_profile_revision_id = profile.id
        state.status = ProfileStatus.ACTIVE.value
        state.last_survey_response_id = survey_input.survey_response_id
        state.last_survey_response_revision = survey_input.response_revision
        self._session.flush()
        return profile


def _active_mapper(session: Session) -> MapperVersion:
    mapper = session.scalar(
        select(MapperVersion).where(
            MapperVersion.version == "survey_mapper_v1",
            MapperVersion.status == "active",
        ),
    )
    if mapper is None:
        raise ValueError("active survey_mapper_v1 mapper version is missing")
    return mapper


def _active_vector_schema(session: Session) -> VectorSchemaVersion:
    vector_schema = session.scalar(
        select(VectorSchemaVersion).where(
            VectorSchemaVersion.version == TASTE_V1_NAME,
            VectorSchemaVersion.status == "active",
        ),
    )
    if vector_schema is None:
        raise ValueError("active taste_v1 vector schema is missing")
    return vector_schema


def _active_beverage_scoring(session: Session) -> ScoringConfig:
    scoring = session.scalar(
        select(ScoringConfig).where(
            ScoringConfig.version == "scoring_v1",
            ScoringConfig.target_type == "beverage",
            ScoringConfig.category == "all",
            ScoringConfig.status == "active",
        ),
    )
    if scoring is None:
        raise ValueError("active beverage scoring_v1 config is missing")
    return scoring


def _ensure_profile_vector(
    session: Session,
    profile: TasteProfileRevision,
    *,
    generated: GeneratedProfile | None = None,
) -> RecommendationVector:
    source_hash = (
        generated.source_snapshot_hash
        if generated is not None
        else str(profile.generation_metadata_json.get("source_snapshot_hash") or "")
    )
    if not source_hash:
        source_hash = f"profile_revision:{profile.id}"
    existing = session.scalar(
        select(RecommendationVector).where(
            RecommendationVector.owner_type == VectorOwnerType.PROFILE_REVISION.value,
            RecommendationVector.owner_id == profile.id,
            RecommendationVector.vector_schema_version_id
            == profile.vector_schema_version_id,
            RecommendationVector.source_hash == source_hash,
        ),
    )
    if existing is not None:
        return existing
    vector = RecommendationVector(
        owner_type=VectorOwnerType.PROFILE_REVISION.value,
        owner_id=profile.id,
        vector_schema_version_id=profile.vector_schema_version_id,
        vector=list(generated.taste_vector if generated else profile.taste_vector),
        vector_json=dict(
            generated.taste_vector_json if generated else profile.taste_vector_json,
        ),
        confidence_json=dict(
            generated.confidence_json if generated else profile.confidence_json,
        ),
        source_hash=source_hash,
        source_metadata_json={
            "survey_response_id": profile.survey_response_id,
            "survey_response_revision": profile.survey_response_revision,
            "mapper_version_id": str(profile.mapper_version_id),
            "vector_schema_version_id": str(profile.vector_schema_version_id),
            "profile_revision": profile.profile_revision,
        },
    )
    session.add(vector)
    return vector


def _add_weights(
    scores: dict[str, float],
    evidence_count: dict[str, int],
    weights: dict[str, float],
) -> None:
    for dimension, weight in weights.items():
        if dimension in scores:
            scores[dimension] = max(scores[dimension], float(weight))
            evidence_count[dimension] += 1


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _hash_json(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
