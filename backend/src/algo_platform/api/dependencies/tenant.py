"""Tenant resolution: X-Org-Id header -> membership -> role/permissions."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Request

from algo_platform.api.dependencies.auth import CurrentUser, CurrentUserDep
from algo_platform.api.dependencies.core import SessionDep
from algo_platform.modules.organizations.application.security_service import (
    OrgSecurityService,
)
from algo_platform.modules.organizations.domain.organizations import MembershipStatus
from algo_platform.modules.organizations.domain.roles import (
    Permission,
    Role,
    permissions_for,
)
from algo_platform.modules.organizations.infrastructure.repositories import (
    SqlMembershipRepository,
)
from algo_platform.shared.domain.errors import PermissionDenied, ValidationFailed
from algo_platform.shared.domain.types import TenantId

ORG_HEADER = "X-Org-Id"

_API_KEY_READ_PERMISSIONS = frozenset(
    {
        Permission.ORG_VIEW,
        Permission.BROKERS_VIEW,
        Permission.STRATEGIES_VIEW,
        Permission.TRADING_VIEW,
        Permission.RISK_VIEW,
        Permission.ANALYTICS_VIEW,
    }
)
_API_KEY_TRADE_PERMISSIONS = _API_KEY_READ_PERMISSIONS | frozenset(
    {Permission.TRADING_EXECUTE, Permission.STRATEGIES_MANAGE}
)


@dataclass(frozen=True, slots=True)
class TenantContext:
    organization_id: TenantId
    role: Role
    permissions: frozenset[Permission]
    user: CurrentUser

    def has(self, permission: Permission) -> bool:
        return permission in self.permissions


async def get_tenant_context(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
) -> TenantContext:
    header = request.headers.get(ORG_HEADER, "").strip()
    if not header:
        raise ValidationFailed(f"{ORG_HEADER} header is required for tenant-scoped routes")
    try:
        organization_id = TenantId(UUID(header))
    except ValueError as error:
        raise ValidationFailed(f"{ORG_HEADER} must be a UUID") from error

    if user.auth_kind == "api_key" and user.api_key_organization_id != organization_id:
        raise PermissionDenied("API key does not belong to this organization")

    memberships = SqlMembershipRepository(session)
    membership = await memberships.get_for_user(organization_id, user.user_id)
    if membership is None or membership.status != MembershipStatus.ACTIVE:
        raise PermissionDenied("you are not a member of this organization")

    # Enterprise IP allowlist: a no-op unless the org configured entries.
    client_ip = request.client.host if request.client else None
    if not await OrgSecurityService(session).is_request_allowed(organization_id, client_ip):
        raise PermissionDenied("your IP address is not allowed to access this organization")

    permissions = permissions_for(membership.role)
    if user.auth_kind == "api_key":
        scoped = (
            _API_KEY_TRADE_PERMISSIONS
            if "trade" in user.api_key_scopes
            else _API_KEY_READ_PERMISSIONS
        )
        permissions = permissions & scoped

    return TenantContext(
        organization_id=organization_id,
        role=membership.role,
        permissions=permissions,
        user=user,
    )


TenantDep = Annotated[TenantContext, Depends(get_tenant_context)]


def require_permission(
    *required: Permission,
) -> Callable[[TenantContext], Coroutine[Any, Any, TenantContext]]:
    async def dependency(tenant: TenantDep) -> TenantContext:
        missing = [p for p in required if p not in tenant.permissions]
        if missing:
            raise PermissionDenied("missing permission: " + ", ".join(p.value for p in missing))
        return tenant

    return dependency
