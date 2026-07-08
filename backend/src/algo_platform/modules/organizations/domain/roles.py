"""Roles and granular permissions for organization members (RBAC)."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    TRADER = "trader"
    VIEWER = "viewer"


class Permission(StrEnum):
    ORG_VIEW = "org:view"
    ORG_MANAGE = "org:manage"
    MEMBERS_MANAGE = "members:manage"
    BILLING_MANAGE = "billing:manage"
    BROKERS_VIEW = "brokers:view"
    BROKERS_MANAGE = "brokers:manage"
    STRATEGIES_VIEW = "strategies:view"
    STRATEGIES_MANAGE = "strategies:manage"
    TRADING_VIEW = "trading:view"
    TRADING_EXECUTE = "trading:execute"
    RISK_VIEW = "risk:view"
    RISK_MANAGE = "risk:manage"
    ANALYTICS_VIEW = "analytics:view"
    AUDIT_VIEW = "audit:view"
    API_KEYS_MANAGE = "api-keys:manage"


_VIEWER_PERMISSIONS = frozenset(
    {
        Permission.ORG_VIEW,
        Permission.BROKERS_VIEW,
        Permission.STRATEGIES_VIEW,
        Permission.TRADING_VIEW,
        Permission.RISK_VIEW,
        Permission.ANALYTICS_VIEW,
    }
)

_TRADER_PERMISSIONS = _VIEWER_PERMISSIONS | frozenset(
    {
        Permission.STRATEGIES_MANAGE,
        Permission.TRADING_EXECUTE,
        Permission.API_KEYS_MANAGE,
    }
)

_ADMIN_PERMISSIONS = frozenset(Permission)

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: _ADMIN_PERMISSIONS,
    Role.ADMIN: _ADMIN_PERMISSIONS,
    Role.TRADER: _TRADER_PERMISSIONS,
    Role.VIEWER: _VIEWER_PERMISSIONS,
}


def permissions_for(role: Role) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[role]
