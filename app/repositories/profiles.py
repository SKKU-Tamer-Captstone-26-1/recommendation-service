import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import ProfileStatus
from app.models.profile import TasteProfileRevision, UserProfileState


class ProfileRepository:
    """Read-only access to derived profile state."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_profile_state(self, external_user_id: str) -> UserProfileState | None:
        statement = select(UserProfileState).where(
            UserProfileState.external_user_id == external_user_id,
        )
        return self._session.scalar(statement)

    def get_profile_revision(
        self,
        profile_revision_id: uuid.UUID,
    ) -> TasteProfileRevision | None:
        statement = select(TasteProfileRevision).where(
            TasteProfileRevision.id == profile_revision_id,
        )
        return self._session.scalar(statement)

    def get_active_profile_revision(
        self,
        external_user_id: str,
    ) -> TasteProfileRevision | None:
        statement = (
            select(TasteProfileRevision)
            .join(
                UserProfileState,
                UserProfileState.active_profile_revision_id == TasteProfileRevision.id,
            )
            .where(UserProfileState.external_user_id == external_user_id)
            .where(UserProfileState.status == ProfileStatus.ACTIVE.value)
            .where(TasteProfileRevision.status == ProfileStatus.ACTIVE.value)
        )
        return self._session.scalar(statement)
