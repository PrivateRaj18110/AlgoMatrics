from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UserProfileDTO:
    id: UUID
    email: str
    full_name: str
    status: str
    email_verified: bool
    mfa_enabled: bool
    avatar_url: str | None
    timezone: str
    theme: str
    preferences: dict[str, Any]
    notification_settings: dict[str, bool]
    is_platform_admin: bool
    created_at: datetime
    last_login_at: datetime | None


@dataclass(frozen=True, slots=True)
class IssuedTokensDTO:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
    session_id: UUID
    user: UserProfileDTO


@dataclass(frozen=True, slots=True)
class LoginResultDTO:
    kind: Literal["tokens", "mfa_required"]
    tokens: IssuedTokensDTO | None = None
    mfa_token: str | None = None


@dataclass(frozen=True, slots=True)
class SessionInfoDTO:
    id: UUID
    user_agent: str
    created_at: datetime
    last_seen_at: datetime
    is_current: bool


@dataclass(frozen=True, slots=True)
class MfaEnrollmentDTO:
    secret: str
    provisioning_uri: str


@dataclass(frozen=True, slots=True)
class ApiKeyDTO:
    id: UUID
    name: str
    prefix: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class CreatedApiKeyDTO:
    key: ApiKeyDTO
    secret: str
