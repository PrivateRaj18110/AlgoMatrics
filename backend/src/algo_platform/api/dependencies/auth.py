"""Authentication dependencies: bearer JWT or API-key principals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, Request

from algo_platform.api.dependencies.core import JwtDep, RedisDep, SessionDep
from algo_platform.modules.identity.application.auth_service import (
    SESSION_CACHE_TTL_SECONDS,
    session_cache_key,
)
from algo_platform.modules.identity.infrastructure.repositories import (
    SqlApiKeyRepository,
    SqlSessionRepository,
    SqlUserRepository,
)
from algo_platform.shared.domain.errors import AuthenticationFailed
from algo_platform.shared.domain.types import UserId, utc_now
from algo_platform.shared.infrastructure.security import hash_token


@dataclass(frozen=True, slots=True)
class CurrentUser:
    user_id: UserId
    email: str
    is_platform_admin: bool
    auth_kind: Literal["jwt", "api_key"]
    session_id: UUID | None = None
    api_key_id: UUID | None = None
    api_key_organization_id: UUID | None = None
    api_key_scopes: frozenset[str] = frozenset()


async def get_current_user(
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    jwt: JwtDep,
) -> CurrentUser:
    authorization = request.headers.get("Authorization", "")
    api_key_header = request.headers.get("X-API-Key", "")

    if authorization.startswith("Bearer "):
        return await _authenticate_jwt(authorization[7:], session, redis, jwt)
    if api_key_header:
        return await _authenticate_api_key(api_key_header, session)
    raise AuthenticationFailed("authentication required")


async def _authenticate_jwt(
    token: str,
    session: SessionDep,
    redis: RedisDep,
    jwt: JwtDep,
) -> CurrentUser:
    claims = jwt.verify(token)
    cache_key = session_cache_key(claims.session_id)
    cached = await redis.get_str(cache_key)
    if cached is None:
        sessions = SqlSessionRepository(session)
        auth_session = await sessions.get(claims.session_id)
        if auth_session is None or not auth_session.is_active:
            raise AuthenticationFailed("session has been revoked")
        await redis.set_str(cache_key, "1", ttl_seconds=SESSION_CACHE_TTL_SECONDS)
    return CurrentUser(
        user_id=UserId(claims.user_id),
        email=claims.email,
        is_platform_admin=claims.is_platform_admin,
        auth_kind="jwt",
        session_id=claims.session_id,
    )


async def _authenticate_api_key(raw_key: str, session: SessionDep) -> CurrentUser:
    api_keys = SqlApiKeyRepository(session)
    key = await api_keys.get_by_hash(hash_token(raw_key))
    if key is None or not key.is_active:
        raise AuthenticationFailed("API key is invalid or revoked")
    users = SqlUserRepository(session)
    user = await users.get(key.user_id)
    if user is None:
        raise AuthenticationFailed("API key owner no longer exists")
    user.ensure_can_authenticate()
    key.last_used_at = utc_now()
    await api_keys.save(key)
    return CurrentUser(
        user_id=key.user_id,
        email=user.email,
        is_platform_admin=False,
        auth_kind="api_key",
        api_key_id=key.id,
        api_key_organization_id=key.organization_id,
        api_key_scopes=frozenset(key.scopes),
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def require_platform_admin(user: CurrentUserDep) -> CurrentUser:
    if not user.is_platform_admin or user.auth_kind != "jwt":
        from algo_platform.shared.domain.errors import PermissionDenied

        raise PermissionDenied("platform administrator access required")
    return user


PlatformAdminDep = Annotated[CurrentUser, Depends(require_platform_admin)]
