from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from algo_platform.api.dependencies.core import SessionDep, SettingsDep
from algo_platform.modules.identity.application.directory import UserDirectory
from algo_platform.modules.organizations.application.service import OrganizationService
from algo_platform.modules.organizations.infrastructure.repositories import (
    SqlInvitationRepository,
    SqlMembershipRepository,
    SqlOrganizationRepository,
)
from algo_platform.shared.infrastructure.email_outbox import TransactionalEmailSender


def get_organization_service(
    session: SessionDep,
    settings: SettingsDep,
) -> OrganizationService:
    return OrganizationService(
        organizations=SqlOrganizationRepository(session),
        memberships=SqlMembershipRepository(session),
        invitations=SqlInvitationRepository(session),
        directory=UserDirectory(session),
        email_sender=TransactionalEmailSender(session),
        settings=settings,
    )


OrganizationServiceDep = Annotated[OrganizationService, Depends(get_organization_service)]
