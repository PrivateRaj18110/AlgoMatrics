"""Organization, membership, and invitation use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog

from algo_platform.config import Settings
from algo_platform.modules.identity.application.directory import UserDirectory
from algo_platform.modules.organizations.domain.organizations import (
    Invitation,
    Membership,
    Organization,
)
from algo_platform.modules.organizations.domain.repositories import (
    InvitationRepository,
    MembershipRepository,
    OrganizationRepository,
)
from algo_platform.modules.organizations.domain.roles import Role
from algo_platform.shared.application.ports import EmailMessage, EmailSender
from algo_platform.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    PermissionDenied,
    ValidationFailed,
)
from algo_platform.shared.domain.types import TenantId, UserId
from algo_platform.shared.infrastructure.security import (
    generate_opaque_token,
    hash_token,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class OrganizationDTO:
    id: UUID
    name: str
    slug: str
    role: str
    settings: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class MemberDTO:
    membership_id: UUID
    user_id: UUID
    email: str
    full_name: str
    role: str
    status: str
    joined_at: datetime


@dataclass(frozen=True, slots=True)
class InvitationDTO:
    id: UUID
    email: str
    role: str
    invited_by: UUID
    expires_at: datetime
    created_at: datetime


class OrganizationService:
    def __init__(
        self,
        *,
        organizations: OrganizationRepository,
        memberships: MembershipRepository,
        invitations: InvitationRepository,
        directory: UserDirectory,
        email_sender: EmailSender,
        settings: Settings,
    ) -> None:
        self._organizations = organizations
        self._memberships = memberships
        self._invitations = invitations
        self._directory = directory
        self._email_sender = email_sender
        self._settings = settings

    async def create_organization(self, *, name: str, owner_user_id: UserId) -> Organization:
        organization = Organization.create(name=name, created_by=owner_user_id)
        await self._organizations.add(organization)
        await self._memberships.add(
            Membership.create(
                organization_id=organization.id, user_id=owner_user_id, role=Role.OWNER
            )
        )
        logger.info(
            "organizations.created",
            organization_id=str(organization.id),
            owner=str(owner_user_id),
        )
        return organization

    async def list_for_user(self, user_id: UserId) -> list[OrganizationDTO]:
        pairs = await self._organizations.list_for_user(user_id)
        return [
            OrganizationDTO(
                id=org.id,
                name=org.name,
                slug=org.slug,
                role=member.role.value,
                settings=dict(org.settings),
                created_at=org.created_at,
            )
            for org, member in pairs
        ]

    async def get(self, organization_id: TenantId, *, role: Role) -> OrganizationDTO:
        organization = await self._organizations.get(organization_id)
        if organization is None:
            raise NotFoundError("organization not found")
        return OrganizationDTO(
            id=organization.id,
            name=organization.name,
            slug=organization.slug,
            role=role.value,
            settings=dict(organization.settings),
            created_at=organization.created_at,
        )

    async def update(
        self,
        organization_id: TenantId,
        *,
        name: str | None,
        settings: dict[str, Any] | None,
        role: Role,
    ) -> OrganizationDTO:
        organization = await self._organizations.get(organization_id)
        if organization is None:
            raise NotFoundError("organization not found")
        if name is not None:
            organization.rename(name)
        if settings is not None:
            allowed_keys = {"default_currency", "week_start", "live_trading_enabled"}
            unknown = set(settings) - allowed_keys
            if unknown:
                raise ValidationFailed(f"unknown settings: {', '.join(sorted(unknown))}")
            organization.update_settings(settings)
        await self._organizations.save(organization)
        return await self.get(organization_id, role=role)

    # -- members ---------------------------------------------------------------

    async def list_members(self, organization_id: TenantId) -> list[MemberDTO]:
        memberships = await self._memberships.list_for_organization(organization_id)
        users = await self._directory.get_many([m.user_id for m in memberships])
        members: list[MemberDTO] = []
        for membership in memberships:
            summary = users.get(membership.user_id)
            if summary is None:
                continue
            members.append(
                MemberDTO(
                    membership_id=membership.id,
                    user_id=membership.user_id,
                    email=summary.email,
                    full_name=summary.full_name,
                    role=membership.role.value,
                    status=membership.status.value,
                    joined_at=membership.created_at,
                )
            )
        return members

    async def change_member_role(
        self,
        organization_id: TenantId,
        *,
        membership_id: UUID,
        new_role: Role,
        acting_role: Role,
    ) -> None:
        membership = await self._memberships.get(membership_id)
        if membership is None or membership.organization_id != organization_id:
            raise NotFoundError("member not found")
        if membership.role == Role.OWNER and acting_role != Role.OWNER:
            raise PermissionDenied("only an owner can change another owner's role")
        if new_role == Role.OWNER and acting_role != Role.OWNER:
            raise PermissionDenied("only an owner can grant ownership")
        if (
            membership.role == Role.OWNER
            and new_role != Role.OWNER
            and await self._memberships.count_owners(organization_id) <= 1
        ):
            raise ConflictError("organization must keep at least one owner")
        membership.change_role(new_role)
        await self._memberships.save(membership)

    async def remove_member(
        self,
        organization_id: TenantId,
        *,
        membership_id: UUID,
        acting_user_id: UserId,
        acting_role: Role,
    ) -> None:
        membership = await self._memberships.get(membership_id)
        if membership is None or membership.organization_id != organization_id:
            raise NotFoundError("member not found")
        if membership.user_id == acting_user_id:
            raise ConflictError("use the leave endpoint to remove yourself")
        if membership.role == Role.OWNER:
            if acting_role != Role.OWNER:
                raise PermissionDenied("only an owner can remove another owner")
            if await self._memberships.count_owners(organization_id) <= 1:
                raise ConflictError("organization must keep at least one owner")
        await self._memberships.remove(membership_id)

    async def leave(self, organization_id: TenantId, *, user_id: UserId) -> None:
        membership = await self._memberships.get_for_user(organization_id, user_id)
        if membership is None:
            raise NotFoundError("you are not a member of this organization")
        if (
            membership.role == Role.OWNER
            and await self._memberships.count_owners(organization_id) <= 1
        ):
            raise ConflictError("transfer ownership before leaving the organization")
        await self._memberships.remove(membership.id)

    # -- invitations -------------------------------------------------------------

    async def invite_member(
        self,
        organization_id: TenantId,
        *,
        email: str,
        role: Role,
        invited_by: UserId,
    ) -> InvitationDTO:
        organization = await self._organizations.get(organization_id)
        if organization is None:
            raise NotFoundError("organization not found")
        normalized = email.strip().lower()
        existing_user = await self._directory.get_by_email(normalized)
        if existing_user is not None:
            existing_membership = await self._memberships.get_for_user(
                organization_id, UserId(existing_user.id)
            )
            if existing_membership is not None:
                raise ConflictError("this user is already a member")
        pending = await self._invitations.get_pending_by_email(organization_id, normalized)
        if pending is not None:
            raise ConflictError("an invitation for this e-mail is already pending")

        raw_token = generate_opaque_token(32)
        invitation = Invitation.create(
            organization_id=organization_id,
            email=normalized,
            role=role,
            token_hash=hash_token(raw_token),
            invited_by=invited_by,
        )
        await self._invitations.add(invitation)
        link = f"{self._settings.app_base_url}/invitations/accept?token={raw_token}"
        await self._email_sender.send(
            EmailMessage(
                to=normalized,
                subject=f"You are invited to {organization.name} on Algo Matrics",
                text=(
                    f"You have been invited to join '{organization.name}' as {role.value}.\n\n"
                    f"Accept the invitation:\n{link}\n\n"
                    "The invitation expires in 7 days. You need an Algo Matrics account "
                    "registered under this e-mail address."
                ),
            )
        )
        return InvitationDTO(
            id=invitation.id,
            email=invitation.email,
            role=invitation.role.value,
            invited_by=invitation.invited_by,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
        )

    async def list_invitations(self, organization_id: TenantId) -> list[InvitationDTO]:
        pending = await self._invitations.list_pending_for_organization(organization_id)
        return [
            InvitationDTO(
                id=i.id,
                email=i.email,
                role=i.role.value,
                invited_by=i.invited_by,
                expires_at=i.expires_at,
                created_at=i.created_at,
            )
            for i in pending
        ]

    async def revoke_invitation(self, organization_id: TenantId, invitation_id: UUID) -> None:
        invitation = await self._invitations.get(invitation_id)
        if invitation is None or invitation.organization_id != organization_id:
            raise NotFoundError("invitation not found")
        invitation.revoke()
        await self._invitations.save(invitation)

    async def accept_invitation(
        self, *, raw_token: str, user_id: UserId, user_email: str
    ) -> OrganizationDTO:
        invitation = await self._invitations.get_by_hash(hash_token(raw_token))
        if invitation is None:
            raise NotFoundError("invitation not found or expired")
        if invitation.email != user_email.strip().lower():
            raise PermissionDenied("this invitation was issued for a different e-mail address")
        existing = await self._memberships.get_for_user(invitation.organization_id, user_id)
        if existing is not None:
            raise ConflictError("you are already a member of this organization")
        invitation.accept()
        await self._invitations.save(invitation)
        await self._memberships.add(
            Membership.create(
                organization_id=invitation.organization_id,
                user_id=user_id,
                role=invitation.role,
                invited_by=invitation.invited_by,
            )
        )
        return await self.get(invitation.organization_id, role=invitation.role)
