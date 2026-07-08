"""Identity aggregate: users, sessions, refresh tokens, one-time e-mail tokens."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from algo_platform.shared.domain.errors import (
    AuthenticationFailed,
    ConflictError,
    InvariantViolation,
)
from algo_platform.shared.domain.types import UserId, utc_now

DEFAULT_NOTIFICATION_SETTINGS: dict[str, bool] = {
    "email_order_fills": True,
    "email_risk_alerts": True,
    "email_billing": True,
    "email_strategy_status": True,
    "inapp_order_fills": True,
    "inapp_risk_alerts": True,
    "inapp_billing": True,
    "inapp_strategy_status": True,
}


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


class Theme(StrEnum):
    DARK = "dark"
    LIGHT = "light"
    SYSTEM = "system"


@dataclass(slots=True)
class User:
    id: UserId
    email: str
    full_name: str
    password_hash: str
    status: UserStatus = UserStatus.ACTIVE
    email_verified_at: datetime | None = None
    mfa_enabled: bool = False
    mfa_secret_ciphertext: str | None = None
    mfa_secret_wrapped_dek: str | None = None
    mfa_pending_secret_ciphertext: str | None = None
    mfa_pending_wrapped_dek: str | None = None
    avatar_path: str | None = None
    timezone: str = "UTC"
    theme: Theme = Theme.SYSTEM
    preferences: dict[str, Any] = field(default_factory=dict)
    notification_settings: dict[str, bool] = field(
        default_factory=lambda: dict(DEFAULT_NOTIFICATION_SETTINGS)
    )
    is_platform_admin: bool = False
    password_changed_at: datetime | None = None
    last_login_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 1

    @classmethod
    def register(
        cls, *, email: str, full_name: str, password_hash: str, user_id: UserId | None = None
    ) -> User:
        normalized = email.strip().lower()
        if "@" not in normalized:
            raise InvariantViolation("email must contain a domain")
        return cls(
            id=user_id or UserId(uuid4()),
            email=normalized,
            full_name=full_name.strip(),
            password_hash=password_hash,
        )

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None

    def ensure_can_authenticate(self) -> None:
        if self.status is UserStatus.SUSPENDED:
            raise AuthenticationFailed("account is suspended")
        if self.status is UserStatus.DEACTIVATED:
            raise AuthenticationFailed("account is deactivated")

    def mark_email_verified(self) -> None:
        if self.email_verified_at is not None:
            raise ConflictError("email is already verified")
        self.email_verified_at = utc_now()

    def record_login(self) -> None:
        self.last_login_at = utc_now()

    def change_password(self, new_hash: str) -> None:
        self.password_hash = new_hash
        self.password_changed_at = utc_now()

    def enable_mfa(self, *, secret_ciphertext: str, wrapped_dek: str) -> None:
        self.mfa_enabled = True
        self.mfa_secret_ciphertext = secret_ciphertext
        self.mfa_secret_wrapped_dek = wrapped_dek
        self.mfa_pending_secret_ciphertext = None
        self.mfa_pending_wrapped_dek = None

    def disable_mfa(self) -> None:
        if not self.mfa_enabled:
            raise ConflictError("MFA is not enabled")
        self.mfa_enabled = False
        self.mfa_secret_ciphertext = None
        self.mfa_secret_wrapped_dek = None

    def suspend(self) -> None:
        if self.status is UserStatus.SUSPENDED:
            raise ConflictError("user is already suspended")
        self.status = UserStatus.SUSPENDED

    def reactivate(self) -> None:
        self.status = UserStatus.ACTIVE


@dataclass(slots=True)
class AuthSession:
    id: UUID
    user_id: UserId
    user_agent: str
    ip_hash: str
    created_at: datetime = field(default_factory=utc_now)
    last_seen_at: datetime = field(default_factory=utc_now)
    revoked_at: datetime | None = None

    @classmethod
    def start(cls, *, user_id: UserId, user_agent: str, ip_hash: str) -> AuthSession:
        return cls(id=uuid4(), user_id=user_id, user_agent=user_agent[:400], ip_hash=ip_hash)

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def touch(self) -> None:
        self.last_seen_at = utc_now()

    def revoke(self) -> None:
        if self.revoked_at is None:
            self.revoked_at = utc_now()


@dataclass(slots=True)
class RefreshToken:
    id: UUID
    user_id: UserId
    session_id: UUID
    family_id: UUID
    token_hash: str
    expires_at: datetime
    created_at: datetime = field(default_factory=utc_now)
    revoked_at: datetime | None = None
    replaced_by_id: UUID | None = None

    @classmethod
    def issue(
        cls,
        *,
        user_id: UserId,
        session_id: UUID,
        token_hash: str,
        ttl_seconds: int,
        family_id: UUID | None = None,
    ) -> RefreshToken:
        return cls(
            id=uuid4(),
            user_id=user_id,
            session_id=session_id,
            family_id=family_id or uuid4(),
            token_hash=token_hash,
            expires_at=utc_now() + timedelta(seconds=ttl_seconds),
        )

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= utc_now()

    @property
    def was_used(self) -> bool:
        return self.replaced_by_id is not None or self.revoked_at is not None

    def rotate_to(self, replacement: RefreshToken) -> None:
        if self.was_used:
            raise InvariantViolation("refresh token already rotated")
        self.replaced_by_id = replacement.id
        self.revoked_at = utc_now()


class EmailTokenPurpose(StrEnum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"  # noqa: S105 - enum label, not a credential


@dataclass(slots=True)
class EmailToken:
    id: UUID
    user_id: UserId
    purpose: EmailTokenPurpose
    token_hash: str
    expires_at: datetime
    created_at: datetime = field(default_factory=utc_now)
    consumed_at: datetime | None = None

    @classmethod
    def issue(
        cls,
        *,
        user_id: UserId,
        purpose: EmailTokenPurpose,
        token_hash: str,
        ttl_seconds: int,
    ) -> EmailToken:
        return cls(
            id=uuid4(),
            user_id=user_id,
            purpose=purpose,
            token_hash=token_hash,
            expires_at=utc_now() + timedelta(seconds=ttl_seconds),
        )

    def consume(self) -> None:
        if self.consumed_at is not None:
            raise AuthenticationFailed("token already used")
        if self.expires_at <= utc_now():
            raise AuthenticationFailed("token expired")
        self.consumed_at = utc_now()


@dataclass(slots=True)
class ApiKey:
    id: UUID
    user_id: UserId
    organization_id: UUID
    name: str
    prefix: str
    key_hash: str
    scopes: list[str]
    created_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        return not (self.expires_at is not None and self.expires_at <= utc_now())

    def revoke(self) -> None:
        if self.revoked_at is not None:
            raise ConflictError("API key already revoked")
        self.revoked_at = utc_now()
