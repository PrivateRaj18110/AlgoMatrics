"""Organization-scoped operational policy read facade."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.organizations.infrastructure.repositories import (
    SqlOrganizationRepository,
)
from algo_platform.shared.domain.types import TenantId


class OrganizationPolicy:
    def __init__(self, session: AsyncSession) -> None:
        self._organizations = SqlOrganizationRepository(session)

    async def live_trading_enabled(self, organization_id: TenantId) -> bool:
        organization = await self._organizations.get(organization_id)
        if organization is None:
            return False
        return organization.settings.get("live_trading_enabled") is True
