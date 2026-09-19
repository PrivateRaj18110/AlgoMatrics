"""Owner approval of new accounts.

Nobody can sign in with an account they created themselves until the platform
owner approves it here. Existing accounts are unaffected.
"""

from __future__ import annotations

import structlog

from algo_platform.config import Settings
from algo_platform.modules.identity.domain.repositories import UserRepository
from algo_platform.modules.identity.domain.users import User
from algo_platform.shared.application.ports import EmailMessage, EmailSender
from algo_platform.shared.domain.errors import NotFoundError
from algo_platform.shared.domain.types import UserId

logger = structlog.get_logger(__name__)


class AccessApprovalService:
    def __init__(
        self, *, users: UserRepository, email_sender: EmailSender, settings: Settings
    ) -> None:
        self._users = users
        self._email_sender = email_sender
        self._settings = settings

    async def _get(self, user_id: UserId) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise NotFoundError("user not found")
        return user

    async def approve(self, user_id: UserId) -> User:
        user = await self._get(user_id)
        user.approve()
        await self._users.save(user)
        verify_hint = (
            ""
            if user.is_email_verified
            else "\nFirst confirm your e-mail address using the link we sent earlier.\n"
        )
        await self._email_sender.send(
            EmailMessage(
                to=user.email,
                subject="Your ALGOMATRIC access was approved",
                text=(
                    f"Hi {user.full_name},\n\n"
                    "Your account has been approved. You can sign in now:\n"
                    f"{self._settings.app_base_url}/login\n{verify_hint}"
                ),
            )
        )
        logger.info("identity.access_approved", user_id=str(user.id))
        return user

    async def reject(self, user_id: UserId) -> User:
        user = await self._get(user_id)
        user.reject()
        await self._users.save(user)
        await self._email_sender.send(
            EmailMessage(
                to=user.email,
                subject="Your ALGOMATRIC access request",
                text=(
                    f"Hi {user.full_name},\n\n"
                    "Your request for an ALGOMATRIC account was not approved. If you "
                    "think this is a mistake, contact the person who invited you."
                ),
            )
        )
        logger.info("identity.access_rejected", user_id=str(user.id))
        return user
