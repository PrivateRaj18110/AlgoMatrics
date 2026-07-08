from __future__ import annotations

from typing import Protocol
from uuid import UUID

from algo_platform.modules.organizations.domain.organizations import (
    Invitation,
    Membership,
    Organization,
)
from algo_platform.shared.domain.types import TenantId, UserId


class OrganizationRepository(Protocol):
    async def add(self, organization: Organization) -> None: ...

    async def get(self, organization_id: TenantId) -> Organization | None: ...

    async def save(self, organization: Organization) -> None: ...

    async def list_for_user(self, user_id: UserId) -> list[tuple[Organization, Membership]]: ...


class MembershipRepository(Protocol):
    async def add(self, membership: Membership) -> None: ...

    async def get(self, membership_id: UUID) -> Membership | None: ...

    async def get_for_user(
        self, organization_id: TenantId, user_id: UserId
    ) -> Membership | None: ...

    async def list_for_organization(self, organization_id: TenantId) -> list[Membership]: ...

    async def count_owners(self, organization_id: TenantId) -> int: ...

    async def save(self, membership: Membership) -> None: ...

    async def remove(self, membership_id: UUID) -> None: ...


class InvitationRepository(Protocol):
    async def add(self, invitation: Invitation) -> None: ...

    async def get(self, invitation_id: UUID) -> Invitation | None: ...

    async def get_by_hash(self, token_hash: str) -> Invitation | None: ...

    async def get_pending_by_email(
        self, organization_id: TenantId, email: str
    ) -> Invitation | None: ...

    async def list_pending_for_organization(
        self, organization_id: TenantId
    ) -> list[Invitation]: ...

    async def save(self, invitation: Invitation) -> None: ...
