from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.organizations.domain.organizations import (
    Invitation,
    Membership,
    MembershipStatus,
    Organization,
)
from algo_platform.modules.organizations.domain.roles import Role
from algo_platform.modules.organizations.infrastructure.models import (
    InvitationModel,
    MembershipModel,
    OrganizationModel,
)
from algo_platform.shared.domain.types import TenantId, UserId, utc_now


def _org_to_entity(model: OrganizationModel) -> Organization:
    return Organization(
        id=TenantId(model.id),
        name=model.name,
        slug=model.slug,
        settings=dict(model.settings),
        created_by=UserId(model.created_by) if model.created_by else None,
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
        deleted_at=model.deleted_at,
    )


def _membership_to_entity(model: MembershipModel) -> Membership:
    return Membership(
        id=model.id,
        organization_id=TenantId(model.organization_id),
        user_id=UserId(model.user_id),
        role=Role(model.role),
        status=MembershipStatus(model.status),
        invited_by=UserId(model.invited_by) if model.invited_by else None,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _invitation_to_entity(model: InvitationModel) -> Invitation:
    return Invitation(
        id=model.id,
        organization_id=TenantId(model.organization_id),
        email=model.email,
        role=Role(model.role),
        token_hash=model.token_hash,
        invited_by=UserId(model.invited_by),
        expires_at=model.expires_at,
        created_at=model.created_at,
        accepted_at=model.accepted_at,
        revoked_at=model.revoked_at,
    )


class SqlOrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, organization: Organization) -> None:
        self._session.add(
            OrganizationModel(
                id=organization.id,
                name=organization.name,
                slug=organization.slug,
                settings=dict(organization.settings),
                created_by=organization.created_by,
                created_at=organization.created_at,
                updated_at=organization.updated_at,
                version=organization.version,
            )
        )
        await self._session.flush()

    async def get(self, organization_id: TenantId) -> Organization | None:
        model = await self._session.get(OrganizationModel, organization_id)
        if model is None or model.deleted_at is not None:
            return None
        return _org_to_entity(model)

    async def save(self, organization: Organization) -> None:
        model = await self._session.get(OrganizationModel, organization.id)
        if model is None:
            raise LookupError(f"organization {organization.id} not found")
        model.name = organization.name
        model.settings = dict(organization.settings)
        model.updated_at = utc_now()
        model.version = organization.version + 1
        model.deleted_at = organization.deleted_at
        await self._session.flush()

    async def list_for_user(self, user_id: UserId) -> list[tuple[Organization, Membership]]:
        result = await self._session.execute(
            select(OrganizationModel, MembershipModel)
            .join(MembershipModel, MembershipModel.organization_id == OrganizationModel.id)
            .where(
                MembershipModel.user_id == user_id,
                MembershipModel.status == MembershipStatus.ACTIVE.value,
                OrganizationModel.deleted_at.is_(None),
            )
            .order_by(OrganizationModel.created_at)
        )
        return [
            (_org_to_entity(org), _membership_to_entity(member))
            for org, member in result.tuples().all()
        ]


class SqlMembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, membership: Membership) -> None:
        self._session.add(
            MembershipModel(
                id=membership.id,
                organization_id=membership.organization_id,
                user_id=membership.user_id,
                role=membership.role.value,
                status=membership.status.value,
                invited_by=membership.invited_by,
                created_at=membership.created_at,
                updated_at=membership.updated_at,
            )
        )
        await self._session.flush()

    async def get(self, membership_id: UUID) -> Membership | None:
        model = await self._session.get(MembershipModel, membership_id)
        return _membership_to_entity(model) if model else None

    async def get_for_user(self, organization_id: TenantId, user_id: UserId) -> Membership | None:
        result = await self._session.execute(
            select(MembershipModel).where(
                MembershipModel.organization_id == organization_id,
                MembershipModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        return _membership_to_entity(model) if model else None

    async def list_for_organization(self, organization_id: TenantId) -> list[Membership]:
        result = await self._session.execute(
            select(MembershipModel)
            .where(MembershipModel.organization_id == organization_id)
            .order_by(MembershipModel.created_at)
        )
        return [_membership_to_entity(m) for m in result.scalars().all()]

    async def count_owners(self, organization_id: TenantId) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(MembershipModel)
            .where(
                MembershipModel.organization_id == organization_id,
                MembershipModel.role == Role.OWNER.value,
                MembershipModel.status == MembershipStatus.ACTIVE.value,
            )
        )
        return int(result.scalar_one())

    async def save(self, membership: Membership) -> None:
        model = await self._session.get(MembershipModel, membership.id)
        if model is None:
            raise LookupError(f"membership {membership.id} not found")
        model.role = membership.role.value
        model.status = membership.status.value
        model.updated_at = utc_now()
        await self._session.flush()

    async def remove(self, membership_id: UUID) -> None:
        await self._session.execute(
            delete(MembershipModel).where(MembershipModel.id == membership_id)
        )


class SqlInvitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, invitation: Invitation) -> None:
        self._session.add(
            InvitationModel(
                id=invitation.id,
                organization_id=invitation.organization_id,
                email=invitation.email,
                role=invitation.role.value,
                token_hash=invitation.token_hash,
                invited_by=invitation.invited_by,
                expires_at=invitation.expires_at,
                created_at=invitation.created_at,
                accepted_at=invitation.accepted_at,
                revoked_at=invitation.revoked_at,
            )
        )
        await self._session.flush()

    async def get(self, invitation_id: UUID) -> Invitation | None:
        model = await self._session.get(InvitationModel, invitation_id)
        return _invitation_to_entity(model) if model else None

    async def get_by_hash(self, token_hash: str) -> Invitation | None:
        result = await self._session.execute(
            select(InvitationModel).where(InvitationModel.token_hash == token_hash)
        )
        model = result.scalar_one_or_none()
        return _invitation_to_entity(model) if model else None

    async def get_pending_by_email(
        self, organization_id: TenantId, email: str
    ) -> Invitation | None:
        result = await self._session.execute(
            select(InvitationModel).where(
                InvitationModel.organization_id == organization_id,
                InvitationModel.email == email.strip().lower(),
                InvitationModel.accepted_at.is_(None),
                InvitationModel.revoked_at.is_(None),
                InvitationModel.expires_at > utc_now(),
            )
        )
        model = result.scalars().first()
        return _invitation_to_entity(model) if model else None

    async def list_pending_for_organization(self, organization_id: TenantId) -> list[Invitation]:
        result = await self._session.execute(
            select(InvitationModel)
            .where(
                InvitationModel.organization_id == organization_id,
                InvitationModel.accepted_at.is_(None),
                InvitationModel.revoked_at.is_(None),
                InvitationModel.expires_at > utc_now(),
            )
            .order_by(InvitationModel.created_at.desc())
        )
        return [_invitation_to_entity(m) for m in result.scalars().all()]

    async def save(self, invitation: Invitation) -> None:
        model = await self._session.get(InvitationModel, invitation.id)
        if model is None:
            raise LookupError(f"invitation {invitation.id} not found")
        model.accepted_at = invitation.accepted_at
        model.revoked_at = invitation.revoked_at
        await self._session.flush()
