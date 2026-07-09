"""Organization security policy: IP allowlist storage + enforcement.

The allowlist is stored under the ``ip_allowlist`` key of the organization's
``settings`` JSON, so no new table is required. An empty allowlist means
unrestricted access (the default for every existing organization).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.organizations.domain.ip_allowlist import (
    is_ip_allowed,
    normalize_entries,
)
from algo_platform.modules.organizations.infrastructure.models import OrganizationModel
from algo_platform.shared.domain.errors import NotFoundError
from algo_platform.shared.domain.types import TenantId, utc_now

_ALLOWLIST_KEY = "ip_allowlist"


class OrgSecurityService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _org(self, organization_id: TenantId) -> OrganizationModel:
        model = (
            await self._session.execute(
                select(OrganizationModel).where(OrganizationModel.id == organization_id)
            )
        ).scalar_one_or_none()
        if model is None or model.deleted_at is not None:
            raise NotFoundError("organization not found")
        return model

    async def get_ip_allowlist(self, organization_id: TenantId) -> list[str]:
        org = await self._org(organization_id)
        raw = org.settings.get(_ALLOWLIST_KEY, [])
        return [str(entry) for entry in raw] if isinstance(raw, list) else []

    async def set_ip_allowlist(
        self, organization_id: TenantId, entries: list[str]
    ) -> list[str]:
        normalized = normalize_entries(entries)
        org = await self._org(organization_id)
        # Reassign a new dict so SQLAlchemy detects the JSON mutation.
        org.settings = {**org.settings, _ALLOWLIST_KEY: normalized}
        org.updated_at = utc_now()
        await self._session.flush()
        return normalized

    async def is_request_allowed(self, organization_id: TenantId, ip: str | None) -> bool:
        """Whether ``ip`` may access the organization. Absent IP ⇒ treated as
        unresolved; allowed only when no allowlist is configured."""

        entries = await self.get_ip_allowlist(organization_id)
        if not entries:
            return True
        return is_ip_allowed(ip or "", entries)
