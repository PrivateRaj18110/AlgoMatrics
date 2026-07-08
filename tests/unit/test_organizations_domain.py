"""Domain tests for the organizations aggregate and RBAC: organization
lifecycle, membership roles, invitations, and role→permission mapping."""

from __future__ import annotations

from uuid import uuid4

import pytest

from algo_platform.modules.organizations.domain.organizations import (
    DEFAULT_ORG_SETTINGS,
    Invitation,
    Membership,
    Organization,
    make_slug,
)
from algo_platform.modules.organizations.domain.roles import (
    Permission,
    Role,
    permissions_for,
)
from algo_platform.shared.domain.errors import ConflictError, InvariantViolation
from algo_platform.shared.domain.types import TenantId, UserId


class TestOrganization:
    def test_create_generates_slug_and_defaults(self) -> None:
        org = Organization.create(name="  Acme Capital  ", created_by=UserId(uuid4()))
        assert org.name == "Acme Capital"
        assert org.slug.startswith("acme-capital-")
        assert org.settings["live_trading_enabled"] is False
        assert org.settings == DEFAULT_ORG_SETTINGS

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(InvariantViolation, match="cannot be empty"):
            Organization.create(name="   ", created_by=UserId(uuid4()))

    def test_rename_and_settings_merge(self) -> None:
        org = Organization.create(name="Acme", created_by=UserId(uuid4()))
        org.rename("Acme Two")
        assert org.name == "Acme Two"
        org.update_settings({"live_trading_enabled": True})
        assert org.settings["live_trading_enabled"] is True
        # Untouched defaults survive the merge.
        assert org.settings["default_currency"] == "INR"
        with pytest.raises(InvariantViolation):
            org.rename("  ")

    def test_slug_falls_back_for_symbol_only_names(self) -> None:
        assert make_slug("***").startswith("org-")


class TestMembership:
    def test_change_role(self) -> None:
        member = Membership.create(
            organization_id=TenantId(uuid4()), user_id=UserId(uuid4()), role=Role.VIEWER
        )
        member.change_role(Role.TRADER)
        assert member.role is Role.TRADER
        with pytest.raises(ConflictError, match="already has this role"):
            member.change_role(Role.TRADER)


class TestInvitation:
    def _invite(self, role: Role = Role.TRADER) -> Invitation:
        return Invitation.create(
            organization_id=TenantId(uuid4()),
            email="  New@Example.com ",
            role=role,
            token_hash="hash",
            invited_by=UserId(uuid4()),
        )

    def test_create_normalizes_email(self) -> None:
        invite = self._invite()
        assert invite.email == "new@example.com"
        assert invite.is_pending

    def test_cannot_invite_as_owner(self) -> None:
        with pytest.raises(InvariantViolation, match="owner"):
            self._invite(role=Role.OWNER)

    def test_accept_once(self) -> None:
        invite = self._invite()
        invite.accept()
        assert not invite.is_pending
        with pytest.raises(ConflictError, match="already accepted"):
            invite.accept()

    def test_revoke_blocks_accept(self) -> None:
        invite = self._invite()
        invite.revoke()
        assert not invite.is_pending
        with pytest.raises(ConflictError, match="revoked"):
            invite.accept()

    def test_revoke_after_accept_conflicts(self) -> None:
        invite = self._invite()
        invite.accept()
        with pytest.raises(ConflictError, match="already accepted"):
            invite.revoke()


class TestRbac:
    def test_owner_and_admin_have_all_permissions(self) -> None:
        assert permissions_for(Role.OWNER) == frozenset(Permission)
        assert permissions_for(Role.ADMIN) == frozenset(Permission)

    def test_role_hierarchy_is_nested(self) -> None:
        viewer = permissions_for(Role.VIEWER)
        trader = permissions_for(Role.TRADER)
        assert viewer < trader
        assert trader < permissions_for(Role.ADMIN)

    def test_trading_execute_is_gated(self) -> None:
        assert Permission.TRADING_VIEW in permissions_for(Role.VIEWER)
        assert Permission.TRADING_EXECUTE not in permissions_for(Role.VIEWER)
        assert Permission.TRADING_EXECUTE in permissions_for(Role.TRADER)

    def test_billing_and_member_management_admin_only(self) -> None:
        assert Permission.BILLING_MANAGE not in permissions_for(Role.TRADER)
        assert Permission.MEMBERS_MANAGE not in permissions_for(Role.TRADER)
        assert Permission.BILLING_MANAGE in permissions_for(Role.ADMIN)
