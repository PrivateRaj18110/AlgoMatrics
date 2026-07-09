from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from algo_platform.api.dependencies.auth import CurrentUserDep
from algo_platform.api.dependencies.core import SessionDep
from algo_platform.api.dependencies.tenant import (
    TenantContext,
    TenantDep,
    require_permission,
)
from algo_platform.modules.audit.application.service import AuditService
from algo_platform.modules.organizations.application.security_service import (
    OrgSecurityService,
)
from algo_platform.modules.organizations.domain.roles import Permission, Role
from algo_platform.modules.organizations.presentation.dependencies import (
    OrganizationServiceDep,
)

router = APIRouter(tags=["organizations"])

OrgManageTenant = Annotated[TenantContext, Depends(require_permission(Permission.ORG_MANAGE))]
MembersManageTenant = Annotated[
    TenantContext, Depends(require_permission(Permission.MEMBERS_MANAGE))
]


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    role: str
    settings: dict[str, Any]
    created_at: datetime


class CreateOrganizationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class UpdateOrganizationRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    settings: dict[str, Any] | None = None


class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    membership_id: UUID
    user_id: UUID
    email: str
    full_name: str
    role: str
    status: str
    joined_at: datetime


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: Literal["admin", "trader", "viewer"]


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: str
    invited_by: UUID
    expires_at: datetime
    created_at: datetime


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ChangeRoleRequest(BaseModel):
    role: Literal["owner", "admin", "trader", "viewer"]


class MessageResponse(BaseModel):
    message: str


@router.get("/organizations", response_model=list[OrganizationResponse])
async def list_my_organizations(
    user: CurrentUserDep, service: OrganizationServiceDep
) -> list[OrganizationResponse]:
    organizations = await service.list_for_user(user.user_id)
    return [OrganizationResponse.model_validate(o) for o in organizations]


@router.post(
    "/organizations",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_organization(
    payload: CreateOrganizationRequest,
    request: Request,
    user: CurrentUserDep,
    service: OrganizationServiceDep,
    session: SessionDep,
) -> OrganizationResponse:
    organization = await service.create_organization(name=payload.name, owner_user_id=user.user_id)
    await AuditService(session).record(
        action="organizations.created",
        resource_type="organization",
        resource_id=str(organization.id),
        organization_id=organization.id,
        actor_user_id=user.user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    dto = await service.get(organization.id, role=Role.OWNER)
    return OrganizationResponse.model_validate(dto)


@router.get("/organizations/current", response_model=OrganizationResponse)
async def get_current_organization(
    tenant: TenantDep, service: OrganizationServiceDep
) -> OrganizationResponse:
    dto = await service.get(tenant.organization_id, role=tenant.role)
    return OrganizationResponse.model_validate(dto)


@router.patch("/organizations/current", response_model=OrganizationResponse)
async def update_current_organization(
    payload: UpdateOrganizationRequest,
    request: Request,
    tenant: OrgManageTenant,
    service: OrganizationServiceDep,
    session: SessionDep,
) -> OrganizationResponse:
    dto = await service.update(
        tenant.organization_id,
        name=payload.name,
        settings=payload.settings,
        role=tenant.role,
    )
    await AuditService(session).record(
        action="organizations.updated",
        resource_type="organization",
        resource_id=str(tenant.organization_id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={"name": payload.name, "settings": payload.settings},
    )
    return OrganizationResponse.model_validate(dto)


# -- security: IP allowlist ---------------------------------------------------------


class IpAllowlistResponse(BaseModel):
    entries: list[str]


class IpAllowlistRequest(BaseModel):
    entries: list[str] = Field(default_factory=list, max_length=100)


@router.get("/organizations/current/ip-allowlist", response_model=IpAllowlistResponse)
async def get_ip_allowlist(
    tenant: OrgManageTenant, session: SessionDep
) -> IpAllowlistResponse:
    entries = await OrgSecurityService(session).get_ip_allowlist(tenant.organization_id)
    return IpAllowlistResponse(entries=entries)


@router.put("/organizations/current/ip-allowlist", response_model=IpAllowlistResponse)
async def set_ip_allowlist(
    payload: IpAllowlistRequest,
    request: Request,
    tenant: OrgManageTenant,
    session: SessionDep,
) -> IpAllowlistResponse:
    entries = await OrgSecurityService(session).set_ip_allowlist(
        tenant.organization_id, payload.entries
    )
    await AuditService(session).record(
        action="organizations.ip_allowlist_updated",
        resource_type="organization",
        resource_id=str(tenant.organization_id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={"ip_allowlist": entries},
    )
    return IpAllowlistResponse(entries=entries)


# -- members ------------------------------------------------------------------------


@router.get("/members", response_model=list[MemberResponse])
async def list_members(tenant: TenantDep, service: OrganizationServiceDep) -> list[MemberResponse]:
    members = await service.list_members(tenant.organization_id)
    return [MemberResponse.model_validate(m) for m in members]


@router.patch("/members/{membership_id}", response_model=MessageResponse)
async def change_member_role(
    membership_id: UUID,
    payload: ChangeRoleRequest,
    request: Request,
    tenant: MembersManageTenant,
    service: OrganizationServiceDep,
    session: SessionDep,
) -> MessageResponse:
    await service.change_member_role(
        tenant.organization_id,
        membership_id=membership_id,
        new_role=Role(payload.role),
        acting_role=tenant.role,
    )
    await AuditService(session).record(
        action="members.role_changed",
        resource_type="membership",
        resource_id=str(membership_id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={"role": payload.role},
    )
    return MessageResponse(message="member role updated")


@router.delete("/members/{membership_id}", response_model=MessageResponse)
async def remove_member(
    membership_id: UUID,
    request: Request,
    tenant: MembersManageTenant,
    service: OrganizationServiceDep,
    session: SessionDep,
) -> MessageResponse:
    await service.remove_member(
        tenant.organization_id,
        membership_id=membership_id,
        acting_user_id=tenant.user.user_id,
        acting_role=tenant.role,
    )
    await AuditService(session).record(
        action="members.removed",
        resource_type="membership",
        resource_id=str(membership_id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return MessageResponse(message="member removed")


@router.post("/members/leave", response_model=MessageResponse)
async def leave_organization(tenant: TenantDep, service: OrganizationServiceDep) -> MessageResponse:
    await service.leave(tenant.organization_id, user_id=tenant.user.user_id)
    return MessageResponse(message="you left the organization")


# -- invitations ------------------------------------------------------------------------


@router.post(
    "/members/invitations",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_member(
    payload: InviteMemberRequest,
    request: Request,
    tenant: MembersManageTenant,
    service: OrganizationServiceDep,
    session: SessionDep,
) -> InvitationResponse:
    invitation = await service.invite_member(
        tenant.organization_id,
        email=payload.email,
        role=Role(payload.role),
        invited_by=tenant.user.user_id,
    )
    await AuditService(session).record(
        action="members.invited",
        resource_type="invitation",
        resource_id=str(invitation.id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={"email": payload.email, "role": payload.role},
    )
    return InvitationResponse.model_validate(invitation)


@router.get("/members/invitations", response_model=list[InvitationResponse])
async def list_invitations(
    tenant: MembersManageTenant, service: OrganizationServiceDep
) -> list[InvitationResponse]:
    invitations = await service.list_invitations(tenant.organization_id)
    return [InvitationResponse.model_validate(i) for i in invitations]


@router.delete("/members/invitations/{invitation_id}", response_model=MessageResponse)
async def revoke_invitation(
    invitation_id: UUID,
    tenant: MembersManageTenant,
    service: OrganizationServiceDep,
) -> MessageResponse:
    await service.revoke_invitation(tenant.organization_id, invitation_id)
    return MessageResponse(message="invitation revoked")


@router.post("/invitations/accept", response_model=OrganizationResponse)
async def accept_invitation(
    payload: AcceptInvitationRequest,
    user: CurrentUserDep,
    service: OrganizationServiceDep,
) -> OrganizationResponse:
    dto = await service.accept_invitation(
        raw_token=payload.token, user_id=user.user_id, user_email=user.email
    )
    return OrganizationResponse.model_validate(dto)
