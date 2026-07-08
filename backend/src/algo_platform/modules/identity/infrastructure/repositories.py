from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.identity.domain.users import (
    ApiKey,
    AuthSession,
    EmailToken,
    EmailTokenPurpose,
    RefreshToken,
    Theme,
    User,
    UserStatus,
)
from algo_platform.modules.identity.infrastructure.models import (
    ApiKeyModel,
    EmailTokenModel,
    RefreshTokenModel,
    SessionModel,
    UserModel,
)
from algo_platform.shared.domain.types import UserId, utc_now


def _user_to_entity(model: UserModel) -> User:
    return User(
        id=UserId(model.id),
        email=model.email,
        full_name=model.full_name,
        password_hash=model.password_hash,
        status=UserStatus(model.status),
        email_verified_at=model.email_verified_at,
        mfa_enabled=model.mfa_enabled,
        mfa_secret_ciphertext=model.mfa_secret_ciphertext,
        mfa_secret_wrapped_dek=model.mfa_secret_wrapped_dek,
        mfa_pending_secret_ciphertext=model.mfa_pending_secret_ciphertext,
        mfa_pending_wrapped_dek=model.mfa_pending_wrapped_dek,
        avatar_path=model.avatar_path,
        timezone=model.timezone,
        theme=Theme(model.theme),
        preferences=dict(model.preferences),
        notification_settings={k: bool(v) for k, v in model.notification_settings.items()},
        is_platform_admin=model.is_platform_admin,
        password_changed_at=model.password_changed_at,
        last_login_at=model.last_login_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )


def _apply_user(model: UserModel, user: User) -> None:
    model.email = user.email
    model.full_name = user.full_name
    model.password_hash = user.password_hash
    model.status = user.status.value
    model.email_verified_at = user.email_verified_at
    model.mfa_enabled = user.mfa_enabled
    model.mfa_secret_ciphertext = user.mfa_secret_ciphertext
    model.mfa_secret_wrapped_dek = user.mfa_secret_wrapped_dek
    model.mfa_pending_secret_ciphertext = user.mfa_pending_secret_ciphertext
    model.mfa_pending_wrapped_dek = user.mfa_pending_wrapped_dek
    model.avatar_path = user.avatar_path
    model.timezone = user.timezone
    model.theme = user.theme.value
    model.preferences = dict(user.preferences)
    model.notification_settings = dict(user.notification_settings)
    model.is_platform_admin = user.is_platform_admin
    model.password_changed_at = user.password_changed_at
    model.last_login_at = user.last_login_at
    model.updated_at = utc_now()
    model.version = user.version + 1


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> None:
        preferences: dict[str, Any] = dict(user.preferences)
        self._session.add(
            UserModel(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                password_hash=user.password_hash,
                status=user.status.value,
                email_verified_at=user.email_verified_at,
                mfa_enabled=user.mfa_enabled,
                avatar_path=user.avatar_path,
                timezone=user.timezone,
                theme=user.theme.value,
                preferences=preferences,
                notification_settings=dict(user.notification_settings),
                is_platform_admin=user.is_platform_admin,
                created_at=user.created_at,
                updated_at=user.updated_at,
                version=user.version,
            )
        )
        await self._session.flush()

    async def get(self, user_id: UserId) -> User | None:
        model = await self._session.get(UserModel, user_id)
        return _user_to_entity(model) if model else None

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.email == email.strip().lower())
        )
        model = result.scalar_one_or_none()
        return _user_to_entity(model) if model else None

    async def save(self, user: User) -> None:
        model = await self._session.get(UserModel, user.id)
        if model is None:
            raise LookupError(f"user {user.id} not found")
        _apply_user(model, user)
        await self._session.flush()


class SqlSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, auth_session: AuthSession) -> None:
        self._session.add(
            SessionModel(
                id=auth_session.id,
                user_id=auth_session.user_id,
                user_agent=auth_session.user_agent,
                ip_hash=auth_session.ip_hash,
                created_at=auth_session.created_at,
                last_seen_at=auth_session.last_seen_at,
                revoked_at=auth_session.revoked_at,
            )
        )
        await self._session.flush()

    async def get(self, session_id: UUID) -> AuthSession | None:
        model = await self._session.get(SessionModel, session_id)
        if model is None:
            return None
        return AuthSession(
            id=model.id,
            user_id=UserId(model.user_id),
            user_agent=model.user_agent,
            ip_hash=model.ip_hash,
            created_at=model.created_at,
            last_seen_at=model.last_seen_at,
            revoked_at=model.revoked_at,
        )

    async def list_active_for_user(self, user_id: UserId) -> list[AuthSession]:
        result = await self._session.execute(
            select(SessionModel)
            .where(SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None))
            .order_by(SessionModel.last_seen_at.desc())
        )
        return [
            AuthSession(
                id=m.id,
                user_id=UserId(m.user_id),
                user_agent=m.user_agent,
                ip_hash=m.ip_hash,
                created_at=m.created_at,
                last_seen_at=m.last_seen_at,
                revoked_at=m.revoked_at,
            )
            for m in result.scalars().all()
        ]

    async def save(self, auth_session: AuthSession) -> None:
        model = await self._session.get(SessionModel, auth_session.id)
        if model is None:
            raise LookupError(f"session {auth_session.id} not found")
        model.last_seen_at = auth_session.last_seen_at
        model.revoked_at = auth_session.revoked_at
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: UserId, *, except_session: UUID | None) -> int:
        stmt = (
            update(SessionModel)
            .where(SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None))
            .values(revoked_at=utc_now())
        )
        if except_session is not None:
            stmt = stmt.where(SessionModel.id != except_session)
        result = await self._session.execute(stmt)
        return int(cast(CursorResult[Any], result).rowcount or 0)


class SqlRefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: RefreshToken) -> None:
        self._session.add(
            RefreshTokenModel(
                id=token.id,
                user_id=token.user_id,
                session_id=token.session_id,
                family_id=token.family_id,
                token_hash=token.token_hash,
                expires_at=token.expires_at,
                created_at=token.created_at,
                revoked_at=token.revoked_at,
                replaced_by_id=token.replaced_by_id,
            )
        )
        await self._session.flush()

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        return await self._get_by_hash(token_hash, for_update=False)

    async def get_by_hash_for_update(self, token_hash: str) -> RefreshToken | None:
        return await self._get_by_hash(token_hash, for_update=True)

    async def _get_by_hash(self, token_hash: str, *, for_update: bool) -> RefreshToken | None:
        statement = select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        if for_update:
            statement = statement.with_for_update()
        result = await self._session.execute(
            statement
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return RefreshToken(
            id=model.id,
            user_id=UserId(model.user_id),
            session_id=model.session_id,
            family_id=model.family_id,
            token_hash=model.token_hash,
            expires_at=model.expires_at,
            created_at=model.created_at,
            revoked_at=model.revoked_at,
            replaced_by_id=model.replaced_by_id,
        )

    async def save(self, token: RefreshToken) -> None:
        model = await self._session.get(RefreshTokenModel, token.id)
        if model is None:
            raise LookupError(f"refresh token {token.id} not found")
        model.revoked_at = token.revoked_at
        model.replaced_by_id = token.replaced_by_id
        await self._session.flush()

    async def revoke_family(self, family_id: UUID) -> int:
        result = await self._session.execute(
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.family_id == family_id,
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=utc_now())
        )
        return int(cast(CursorResult[Any], result).rowcount or 0)

    async def revoke_for_session(self, session_id: UUID) -> int:
        result = await self._session.execute(
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.session_id == session_id,
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=utc_now())
        )
        return int(cast(CursorResult[Any], result).rowcount or 0)


class SqlEmailTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: EmailToken) -> None:
        self._session.add(
            EmailTokenModel(
                id=token.id,
                user_id=token.user_id,
                purpose=token.purpose.value,
                token_hash=token.token_hash,
                expires_at=token.expires_at,
                created_at=token.created_at,
                consumed_at=token.consumed_at,
            )
        )
        await self._session.flush()

    async def get_by_hash(self, token_hash: str, purpose: EmailTokenPurpose) -> EmailToken | None:
        result = await self._session.execute(
            select(EmailTokenModel).where(
                EmailTokenModel.token_hash == token_hash,
                EmailTokenModel.purpose == purpose.value,
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return EmailToken(
            id=model.id,
            user_id=UserId(model.user_id),
            purpose=EmailTokenPurpose(model.purpose),
            token_hash=model.token_hash,
            expires_at=model.expires_at,
            created_at=model.created_at,
            consumed_at=model.consumed_at,
        )

    async def save(self, token: EmailToken) -> None:
        model = await self._session.get(EmailTokenModel, token.id)
        if model is None:
            raise LookupError(f"email token {token.id} not found")
        model.consumed_at = token.consumed_at
        await self._session.flush()

    async def invalidate_for_user(self, user_id: UserId, purpose: EmailTokenPurpose) -> None:
        await self._session.execute(
            update(EmailTokenModel)
            .where(
                EmailTokenModel.user_id == user_id,
                EmailTokenModel.purpose == purpose.value,
                EmailTokenModel.consumed_at.is_(None),
            )
            .values(consumed_at=utc_now())
        )


class SqlApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_entity(model: ApiKeyModel) -> ApiKey:
        return ApiKey(
            id=model.id,
            user_id=UserId(model.user_id),
            organization_id=model.organization_id,
            name=model.name,
            prefix=model.prefix,
            key_hash=model.key_hash,
            scopes=list(model.scopes),
            created_at=model.created_at,
            expires_at=model.expires_at,
            last_used_at=model.last_used_at,
            revoked_at=model.revoked_at,
        )

    async def add(self, key: ApiKey) -> None:
        self._session.add(
            ApiKeyModel(
                id=key.id,
                user_id=key.user_id,
                organization_id=key.organization_id,
                name=key.name,
                prefix=key.prefix,
                key_hash=key.key_hash,
                scopes=list(key.scopes),
                created_at=key.created_at,
                expires_at=key.expires_at,
            )
        )
        await self._session.flush()

    async def get(self, key_id: UUID) -> ApiKey | None:
        model = await self._session.get(ApiKeyModel, key_id)
        return self._to_entity(model) if model else None

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
        result = await self._session.execute(
            select(ApiKeyModel).where(ApiKeyModel.key_hash == key_hash)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_for_organization(self, organization_id: UUID) -> list[ApiKey]:
        result = await self._session.execute(
            select(ApiKeyModel)
            .where(ApiKeyModel.organization_id == organization_id)
            .order_by(ApiKeyModel.created_at.desc())
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def save(self, key: ApiKey) -> None:
        model = await self._session.get(ApiKeyModel, key.id)
        if model is None:
            raise LookupError(f"api key {key.id} not found")
        model.last_used_at = key.last_used_at
        model.revoked_at = key.revoked_at
        await self._session.flush()
