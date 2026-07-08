from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    organization_name: str | None = Field(default=None, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class MfaCompleteRequest(BaseModel):
    mfa_token: str = Field(min_length=10, max_length=200)
    code: str = Field(min_length=6, max_length=8)


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class EmailRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class TokensResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access_token: str
    access_expires_at: datetime
    # Browser routes transport refresh credentials only in an HttpOnly cookie.
    # The service DTO still carries the value internally for rotation.
    refresh_token: str | None = None
    refresh_expires_at: datetime
    session_id: UUID
    user: UserProfileResponse


class LoginResponse(BaseModel):
    kind: Literal["tokens", "mfa_required"]
    tokens: TokensResponse | None = None
    mfa_token: str | None = None


class MessageResponse(BaseModel):
    message: str


class RegisterResponse(BaseModel):
    user_id: UUID
    message: str


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = Field(default=None, max_length=64)
    theme: Literal["dark", "light", "system"] | None = None


class PreferencesRequest(BaseModel):
    preferences: dict[str, Any] = Field(default_factory=dict)


class NotificationSettingsRequest(BaseModel):
    settings: dict[str, bool]


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


class MfaEnrollResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    secret: str
    provisioning_uri: str


class MfaActivateRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class MfaDisableRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=6, max_length=8)


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_agent: str
    created_at: datetime
    last_seen_at: datetime
    is_current: bool


class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    prefix: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[Literal["read", "trade"]] = ["read"]
    expires_in_days: int | None = Field(default=None, ge=1, le=730)


class CreatedApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: ApiKeyResponse
    secret: str


class WsTicketResponse(BaseModel):
    ticket: str
