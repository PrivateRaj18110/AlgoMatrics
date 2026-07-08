from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, UploadFile, status
from fastapi.responses import FileResponse

from algo_platform.api.dependencies.auth import CurrentUserDep
from algo_platform.api.dependencies.core import SessionDep, SettingsDep
from algo_platform.api.dependencies.tenant import TenantContext, require_permission
from algo_platform.modules.audit.application.service import AuditService
from algo_platform.modules.identity.presentation.dependencies import (
    ApiKeyServiceDep,
    UserServiceDep,
)
from algo_platform.modules.identity.presentation.schemas import (
    ApiKeyResponse,
    ChangePasswordRequest,
    CreateApiKeyRequest,
    CreatedApiKeyResponse,
    MessageResponse,
    MfaActivateRequest,
    MfaDisableRequest,
    MfaEnrollResponse,
    NotificationSettingsRequest,
    PreferencesRequest,
    SessionResponse,
    UpdateProfileRequest,
    UserProfileResponse,
)
from algo_platform.modules.organizations.domain.roles import Permission
from algo_platform.shared.domain.errors import AuthenticationFailed, ValidationFailed
from algo_platform.shared.domain.types import UserId

router = APIRouter(tags=["users"])

_ALLOWED_AVATAR_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
_MAX_AVATAR_BYTES = 2 * 1024 * 1024


@router.get("/me", response_model=UserProfileResponse)
async def get_me(user: CurrentUserDep, users: UserServiceDep) -> UserProfileResponse:
    profile = await users.get_profile(user.user_id)
    return UserProfileResponse.model_validate(profile)


@router.patch("/users/me", response_model=UserProfileResponse)
async def update_me(
    payload: UpdateProfileRequest, user: CurrentUserDep, users: UserServiceDep
) -> UserProfileResponse:
    profile = await users.update_profile(
        user.user_id,
        full_name=payload.full_name,
        timezone=payload.timezone,
        theme=payload.theme,
    )
    return UserProfileResponse.model_validate(profile)


@router.put("/users/me/preferences", response_model=UserProfileResponse)
async def update_preferences(
    payload: PreferencesRequest, user: CurrentUserDep, users: UserServiceDep
) -> UserProfileResponse:
    profile = await users.update_preferences(user.user_id, payload.preferences)
    return UserProfileResponse.model_validate(profile)


@router.put("/users/me/notifications", response_model=UserProfileResponse)
async def update_notifications(
    payload: NotificationSettingsRequest, user: CurrentUserDep, users: UserServiceDep
) -> UserProfileResponse:
    profile = await users.update_notification_settings(user.user_id, payload.settings)
    return UserProfileResponse.model_validate(profile)


@router.post("/users/me/password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: CurrentUserDep,
    users: UserServiceDep,
    session: SessionDep,
) -> MessageResponse:
    if user.session_id is None:
        raise AuthenticationFailed("password changes require an interactive session")
    await users.change_password(
        user.user_id,
        current_password=payload.current_password,
        new_password=payload.new_password,
        current_session_id=user.session_id,
    )
    await AuditService(session).record(
        action="users.password_changed",
        resource_type="user",
        resource_id=str(user.user_id),
        actor_user_id=user.user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return MessageResponse(message="password changed; other sessions were signed out")


# -- avatar ---------------------------------------------------------------------


@router.post("/users/me/avatar", response_model=UserProfileResponse)
async def upload_avatar(
    file: UploadFile,
    user: CurrentUserDep,
    users: UserServiceDep,
    settings: SettingsDep,
) -> UserProfileResponse:
    content_type = (file.content_type or "").lower()
    if content_type not in _ALLOWED_AVATAR_TYPES:
        raise ValidationFailed("avatar must be a PNG, JPEG, or WebP image")
    data = await file.read()
    if len(data) > _MAX_AVATAR_BYTES:
        raise ValidationFailed("avatar must be 2 MB or smaller")
    avatar_dir = settings.upload_dir / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{user.user_id}-{secrets.token_hex(6)}{_ALLOWED_AVATAR_TYPES[content_type]}"
    target = avatar_dir / filename
    target.write_bytes(data)
    profile = await users.set_avatar_path(user.user_id, f"avatars/{filename}")
    return UserProfileResponse.model_validate(profile)


@router.delete("/users/me/avatar", response_model=UserProfileResponse)
async def delete_avatar(user: CurrentUserDep, users: UserServiceDep) -> UserProfileResponse:
    profile = await users.set_avatar_path(user.user_id, None)
    return UserProfileResponse.model_validate(profile)


@router.get("/users/{user_id}/avatar", response_class=FileResponse)
async def get_avatar(user_id: UUID, users: UserServiceDep, settings: SettingsDep) -> FileResponse:
    relative = await users.get_avatar_path(UserId(user_id))
    base = settings.upload_dir.resolve()
    target = (base / relative).resolve()
    if not str(target).startswith(str(base)) or not target.is_file():
        from algo_platform.shared.domain.errors import NotFoundError

        raise NotFoundError("avatar not found")
    return FileResponse(Path(target))


# -- MFA -------------------------------------------------------------------------


@router.post("/users/me/mfa/enroll", response_model=MfaEnrollResponse)
async def enroll_mfa(user: CurrentUserDep, users: UserServiceDep) -> MfaEnrollResponse:
    enrollment = await users.start_mfa_enrollment(user.user_id)
    return MfaEnrollResponse.model_validate(enrollment)


@router.post("/users/me/mfa/activate", response_model=MessageResponse)
async def activate_mfa(
    payload: MfaActivateRequest,
    request: Request,
    user: CurrentUserDep,
    users: UserServiceDep,
    session: SessionDep,
) -> MessageResponse:
    await users.activate_mfa(user.user_id, code=payload.code)
    await AuditService(session).record(
        action="users.mfa_enabled",
        resource_type="user",
        resource_id=str(user.user_id),
        actor_user_id=user.user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return MessageResponse(message="two-factor authentication enabled")


@router.post("/users/me/mfa/disable", response_model=MessageResponse)
async def disable_mfa(
    payload: MfaDisableRequest,
    request: Request,
    user: CurrentUserDep,
    users: UserServiceDep,
    session: SessionDep,
) -> MessageResponse:
    await users.disable_mfa(user.user_id, password=payload.password, code=payload.code)
    await AuditService(session).record(
        action="users.mfa_disabled",
        resource_type="user",
        resource_id=str(user.user_id),
        actor_user_id=user.user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return MessageResponse(message="two-factor authentication disabled")


# -- sessions ----------------------------------------------------------------------


@router.get("/users/me/sessions", response_model=list[SessionResponse])
async def list_sessions(user: CurrentUserDep, users: UserServiceDep) -> list[SessionResponse]:
    if user.session_id is None:
        raise AuthenticationFailed("session listing requires an interactive session")
    sessions = await users.list_sessions(user.user_id, current_session_id=user.session_id)
    return [SessionResponse.model_validate(s) for s in sessions]


@router.delete("/users/me/sessions/{session_id}", response_model=MessageResponse)
async def revoke_session(
    session_id: UUID, user: CurrentUserDep, users: UserServiceDep
) -> MessageResponse:
    await users.revoke_session(user.user_id, session_id)
    return MessageResponse(message="session revoked")


@router.post("/users/me/sessions/revoke-others", response_model=MessageResponse)
async def revoke_other_sessions(user: CurrentUserDep, users: UserServiceDep) -> MessageResponse:
    if user.session_id is None:
        raise AuthenticationFailed("session management requires an interactive session")
    count = await users.revoke_other_sessions(user.user_id, current_session_id=user.session_id)
    return MessageResponse(message=f"revoked {count} other session(s)")


# -- API keys (organization-scoped) --------------------------------------------------

api_keys_router = APIRouter(prefix="/api-keys", tags=["api-keys"])

ApiKeysTenant = Annotated[TenantContext, Depends(require_permission(Permission.API_KEYS_MANAGE))]


@api_keys_router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(tenant: ApiKeysTenant, service: ApiKeyServiceDep) -> list[ApiKeyResponse]:
    keys = await service.list(tenant.organization_id)
    return [ApiKeyResponse.model_validate(k) for k in keys]


@api_keys_router.post("", response_model=CreatedApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: CreateApiKeyRequest,
    request: Request,
    tenant: ApiKeysTenant,
    service: ApiKeyServiceDep,
    session: SessionDep,
) -> CreatedApiKeyResponse:
    created = await service.create(
        user_id=tenant.user.user_id,
        organization_id=tenant.organization_id,
        name=payload.name,
        scopes=list(payload.scopes),
        expires_in_days=payload.expires_in_days,
    )
    await AuditService(session).record(
        action="api_keys.created",
        resource_type="api_key",
        resource_id=str(created.key.id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return CreatedApiKeyResponse.model_validate(created)


@api_keys_router.delete("/{key_id}", response_model=MessageResponse)
async def revoke_api_key(
    key_id: UUID,
    request: Request,
    tenant: ApiKeysTenant,
    service: ApiKeyServiceDep,
    session: SessionDep,
) -> MessageResponse:
    await service.revoke(organization_id=tenant.organization_id, key_id=key_id)
    await AuditService(session).record(
        action="api_keys.revoked",
        resource_type="api_key",
        resource_id=str(key_id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return MessageResponse(message="API key revoked")
