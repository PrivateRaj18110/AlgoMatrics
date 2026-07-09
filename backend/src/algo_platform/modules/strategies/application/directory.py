"""Read facade for other bounded contexts: strategy ownership checks."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.strategies.infrastructure.models import StrategyModel
from algo_platform.shared.domain.types import TenantId


class StrategyDirectory:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def owns(self, organization_id: TenantId, strategy_id: UUID) -> bool:
        result = await self._session.execute(
            select(StrategyModel.id).where(
                StrategyModel.id == strategy_id,
                StrategyModel.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none() is not None
