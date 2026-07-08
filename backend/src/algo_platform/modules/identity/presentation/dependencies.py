from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from algo_platform.api.dependencies.core import (
    CipherDep,
    JwtDep,
    RedisDep,
    SessionDep,
    SettingsDep,
)
from algo_platform.modules.identity.application.auth_service import AuthService
from algo_platform.modules.identity.application.user_service import ApiKeyService, UserService
from algo_platform.modules.identity.infrastructure.repositories import (
    SqlApiKeyRepository,
    SqlEmailTokenRepository,
    SqlRefreshTokenRepository,
    SqlSessionRepository,
    SqlUserRepository,
)
from algo_platform.shared.infrastructure.email_outbox import TransactionalEmailSender


def get_auth_service(
    session: SessionDep,
    redis: RedisDep,
    jwt: JwtDep,
    cipher: CipherDep,
    settings: SettingsDep,
) -> AuthService:
    return AuthService(
        session=session,
        users=SqlUserRepository(session),
        sessions=SqlSessionRepository(session),
        refresh_tokens=SqlRefreshTokenRepository(session),
        email_tokens=SqlEmailTokenRepository(session),
        jwt=jwt,
        email_sender=TransactionalEmailSender(session),
        redis=redis,
        cipher=cipher,
        settings=settings,
    )


def get_user_service(
    session: SessionDep,
    redis: RedisDep,
    cipher: CipherDep,
    settings: SettingsDep,
) -> UserService:
    return UserService(
        users=SqlUserRepository(session),
        sessions=SqlSessionRepository(session),
        redis=redis,
        cipher=cipher,
        settings=settings,
    )


def get_api_key_service(session: SessionDep) -> ApiKeyService:
    return ApiKeyService(api_keys=SqlApiKeyRepository(session))


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
ApiKeyServiceDep = Annotated[ApiKeyService, Depends(get_api_key_service)]
