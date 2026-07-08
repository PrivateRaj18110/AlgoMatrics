"""Public read facade other bounded contexts use to resolve user identity."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.identity.infrastructure.models import UserModel


@dataclass(frozen=True, slots=True)
class UserSummaryDTO:
    id: UUID
    email: str
    full_name: str
    status: str
    avatar_url: str | None


class UserDirectory:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_many(self, user_ids: list[UUID]) -> dict[UUID, UserSummaryDTO]:
        if not user_ids:
            return {}
        result = await self._session.execute(select(UserModel).where(UserModel.id.in_(user_ids)))
        summaries = {}
        for model in result.scalars().all():
            summaries[model.id] = UserSummaryDTO(
                id=model.id,
                email=model.email,
                full_name=model.full_name,
                status=model.status,
                avatar_url=f"/api/v1/users/{model.id}/avatar" if model.avatar_path else None,
            )
        return summaries

    async def get_by_email(self, email: str) -> UserSummaryDTO | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.email == email.strip().lower())
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return UserSummaryDTO(
            id=model.id,
            email=model.email,
            full_name=model.full_name,
            status=model.status,
            avatar_url=f"/api/v1/users/{model.id}/avatar" if model.avatar_path else None,
        )
