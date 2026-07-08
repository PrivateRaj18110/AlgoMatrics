"""Small broker-catalog read facade for other bounded contexts."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.brokerage.infrastructure.repositories import (
    SqlBrokerCatalogRepository,
)


@dataclass(frozen=True, slots=True)
class BrokerSummary:
    id: UUID
    code: str
    name: str
    is_active: bool


class BrokerDirectory:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = SqlBrokerCatalogRepository(session)

    async def get(self, broker_id: UUID) -> BrokerSummary | None:
        broker = await self._repository.get(broker_id)
        if broker is None:
            return None
        return BrokerSummary(
            id=broker.id,
            code=broker.code,
            name=broker.name,
            is_active=broker.is_active,
        )
