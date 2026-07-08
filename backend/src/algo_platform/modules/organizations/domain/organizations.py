from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from algo_platform.modules.organizations.domain.roles import Role
from algo_platform.shared.domain.errors import ConflictError, InvariantViolation
from algo_platform.shared.domain.types import TenantId, UserId, utc_now

INVITATION_TTL_SECONDS = 60 * 60 * 24 * 7

DEFAULT_ORG_SETTINGS: dict[str, Any] = {
    "default_currency": "INR",
    "week_start": "monday",
    "live_trading_enabled": False,
}


def make_slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "org"
    return f"{base[:40]}-{secrets.token_hex(3)}"


@dataclass(slots=True)
class Organization:
    id: TenantId
    name: str
    slug: str
    settings: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_ORG_SETTINGS))
    created_by: UserId | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 1
    deleted_at: datetime | None = None

    @classmethod
    def create(cls, *, name: str, created_by: UserId) -> Organization:
        cleaned = name.strip()
        if not cleaned:
            raise InvariantViolation("organization name cannot be empty")
        return cls(
            id=TenantId(uuid4()), name=cleaned, slug=make_slug(cleaned), created_by=created_by
        )

    def rename(self, name: str) -> None:
        cleaned = name.strip()
        if not cleaned:
            raise InvariantViolation("organization name cannot be empty")
        self.name = cleaned

    def update_settings(self, changes: dict[str, Any]) -> None:
        merged = dict(self.settings)
        merged.update(changes)
        self.settings = merged


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


@dataclass(slots=True)
class Membership:
    id: UUID
    organization_id: TenantId
    user_id: UserId
    role: Role
    status: MembershipStatus = MembershipStatus.ACTIVE
    invited_by: UserId | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        *,
        organization_id: TenantId,
        user_id: UserId,
        role: Role,
        invited_by: UserId | None = None,
    ) -> Membership:
        return cls(
            id=uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            role=role,
            invited_by=invited_by,
        )

    def change_role(self, role: Role) -> None:
        if self.role == role:
            raise ConflictError("member already has this role")
        self.role = role
        self.updated_at = utc_now()


@dataclass(slots=True)
class Invitation:
    id: UUID
    organization_id: TenantId
    email: str
    role: Role
    token_hash: str
    invited_by: UserId
    expires_at: datetime
    created_at: datetime = field(default_factory=utc_now)
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        organization_id: TenantId,
        email: str,
        role: Role,
        token_hash: str,
        invited_by: UserId,
    ) -> Invitation:
        if role == Role.OWNER:
            raise InvariantViolation("cannot invite a member as owner")
        return cls(
            id=uuid4(),
            organization_id=organization_id,
            email=email.strip().lower(),
            role=role,
            token_hash=token_hash,
            invited_by=invited_by,
            expires_at=utc_now() + timedelta(seconds=INVITATION_TTL_SECONDS),
        )

    @property
    def is_pending(self) -> bool:
        return self.accepted_at is None and self.revoked_at is None and self.expires_at > utc_now()

    def accept(self) -> None:
        if self.accepted_at is not None:
            raise ConflictError("invitation already accepted")
        if self.revoked_at is not None:
            raise ConflictError("invitation was revoked")
        if self.expires_at <= utc_now():
            raise ConflictError("invitation expired")
        self.accepted_at = utc_now()

    def revoke(self) -> None:
        if self.accepted_at is not None:
            raise ConflictError("invitation already accepted")
        self.revoked_at = utc_now()
