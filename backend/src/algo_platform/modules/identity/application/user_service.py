"""Profile, preferences, password, MFA, session, and API-key use cases."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4
from zoneinfo import available_timezones

from algo_platform.config import Settings
from algo_platform.modules.identity.application.auth_service import (
    session_cache_key,
    user_profile_dto,
    validate_password_strength,
)
from algo_platform.modules.identity.application.dto import (
    ApiKeyDTO,
    CreatedApiKeyDTO,
    MfaEnrollmentDTO,
    SessionInfoDTO,
    UserProfileDTO,
)
from algo_platform.modules.identity.domain.repositories import (
    ApiKeyRepository,
    SessionRepository,
    UserRepository,
)
from algo_platform.modules.identity.domain.users import ApiKey, Theme, User
from algo_platform.shared.domain.errors import (
    AuthenticationFailed,
    ConflictError,
    NotFoundError,
    ValidationFailed,
)
from algo_platform.shared.domain.types import UserId, utc_now
from algo_platform.shared.infrastructure.encryption import CredentialCipher, EncryptedSecret
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway
from algo_platform.shared.infrastructure.security import (
    Totp,
    generate_api_key,
    hash_password,
    verify_password,
)

API_KEY_SCOPES = {"read", "trade"}


class UserService:
    def __init__(
        self,
        *,
        users: UserRepository,
        sessions: SessionRepository,
        redis: RedisGateway,
        cipher: CredentialCipher,
        settings: Settings,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._redis = redis
        self._cipher = cipher
        self._settings = settings

    async def _get_user(self, user_id: UserId) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise NotFoundError("user not found")
        return user

    async def get_profile(self, user_id: UserId) -> UserProfileDTO:
        return user_profile_dto(await self._get_user(user_id))

    async def update_profile(
        self,
        user_id: UserId,
        *,
        full_name: str | None = None,
        timezone: str | None = None,
        theme: str | None = None,
    ) -> UserProfileDTO:
        user = await self._get_user(user_id)
        if full_name is not None:
            cleaned = full_name.strip()
            if not cleaned:
                raise ValidationFailed("full name cannot be empty")
            user.full_name = cleaned
        if timezone is not None:
            user.timezone = _validate_timezone(timezone)
        if theme is not None:
            try:
                user.theme = Theme(theme)
            except ValueError as error:
                raise ValidationFailed("theme must be dark, light, or system") from error
        await self._users.save(user)
        return user_profile_dto(user)

    async def update_preferences(
        self, user_id: UserId, preferences: dict[str, object]
    ) -> UserProfileDTO:
        user = await self._get_user(user_id)
        merged = dict(user.preferences)
        merged.update(preferences)
        user.preferences = merged
        await self._users.save(user)
        return user_profile_dto(user)

    async def update_notification_settings(
        self, user_id: UserId, settings: dict[str, bool]
    ) -> UserProfileDTO:
        user = await self._get_user(user_id)
        merged = dict(user.notification_settings)
        for key, value in settings.items():
            if key not in merged:
                raise ValidationFailed(f"unknown notification setting: {key}")
            merged[key] = bool(value)
        user.notification_settings = merged
        await self._users.save(user)
        return user_profile_dto(user)

    async def set_avatar_path(self, user_id: UserId, path: str | None) -> UserProfileDTO:
        user = await self._get_user(user_id)
        user.avatar_path = path
        await self._users.save(user)
        return user_profile_dto(user)

    async def get_avatar_path(self, user_id: UserId) -> str:
        user = await self._get_user(user_id)
        if not user.avatar_path:
            raise NotFoundError("user has no avatar")
        return user.avatar_path

    async def change_password(
        self,
        user_id: UserId,
        *,
        current_password: str,
        new_password: str,
        current_session_id: UUID,
    ) -> None:
        validate_password_strength(new_password)
        user = await self._get_user(user_id)
        if not verify_password(current_password, user.password_hash):
            raise AuthenticationFailed("current password is incorrect")
        user.change_password(hash_password(new_password))
        await self._users.save(user)
        await self._sessions.revoke_all_for_user(user_id, except_session=current_session_id)

    # -- MFA ------------------------------------------------------------------

    async def start_mfa_enrollment(self, user_id: UserId) -> MfaEnrollmentDTO:
        user = await self._get_user(user_id)
        if user.mfa_enabled:
            raise ConflictError("MFA is already enabled")
        secret = Totp.generate_secret()
        encrypted = self._cipher.encrypt(secret.encode("utf-8"), aad=f"mfa:{user.id}".encode())
        user.mfa_pending_secret_ciphertext = encrypted.ciphertext_b64
        user.mfa_pending_wrapped_dek = encrypted.wrapped_dek_b64
        await self._users.save(user)
        uri = Totp(secret).provisioning_uri(account_name=user.email, issuer="Algo Matrics")
        return MfaEnrollmentDTO(secret=secret, provisioning_uri=uri)

    async def activate_mfa(self, user_id: UserId, *, code: str) -> None:
        user = await self._get_user(user_id)
        if user.mfa_enabled:
            raise ConflictError("MFA is already enabled")
        if not user.mfa_pending_secret_ciphertext or not user.mfa_pending_wrapped_dek:
            raise ValidationFailed("start MFA enrollment first")
        secret = self._decrypt(
            user.mfa_pending_secret_ciphertext,
            user.mfa_pending_wrapped_dek,
            aad=f"mfa:{user.id}".encode(),
        )
        if not Totp(secret).verify(code):
            raise AuthenticationFailed("incorrect authentication code")
        user.enable_mfa(
            secret_ciphertext=user.mfa_pending_secret_ciphertext,
            wrapped_dek=user.mfa_pending_wrapped_dek,
        )
        await self._users.save(user)

    async def disable_mfa(self, user_id: UserId, *, password: str, code: str) -> None:
        user = await self._get_user(user_id)
        if not user.mfa_enabled:
            raise ConflictError("MFA is not enabled")
        if not verify_password(password, user.password_hash):
            raise AuthenticationFailed("password is incorrect")
        if not user.mfa_secret_ciphertext or not user.mfa_secret_wrapped_dek:
            raise ConflictError("MFA secret is missing")
        secret = self._decrypt(
            user.mfa_secret_ciphertext,
            user.mfa_secret_wrapped_dek,
            aad=f"mfa:{user.id}".encode(),
        )
        if not Totp(secret).verify(code):
            raise AuthenticationFailed("incorrect authentication code")
        user.disable_mfa()
        await self._users.save(user)

    def _decrypt(self, ciphertext_b64: str, wrapped_dek_b64: str, *, aad: bytes) -> str:
        return self._cipher.decrypt(
            EncryptedSecret(
                ciphertext_b64=ciphertext_b64,
                wrapped_dek_b64=wrapped_dek_b64,
                key_version=self._settings.credential_key_version,
            ),
            aad=aad,
        ).decode("utf-8")

    # -- sessions ---------------------------------------------------------------

    async def list_sessions(
        self, user_id: UserId, *, current_session_id: UUID
    ) -> list[SessionInfoDTO]:
        sessions = await self._sessions.list_active_for_user(user_id)
        return [
            SessionInfoDTO(
                id=s.id,
                user_agent=s.user_agent,
                created_at=s.created_at,
                last_seen_at=s.last_seen_at,
                is_current=s.id == current_session_id,
            )
            for s in sessions
        ]

    async def revoke_session(self, user_id: UserId, session_id: UUID) -> None:
        target = await self._sessions.get(session_id)
        if target is None or target.user_id != user_id:
            raise NotFoundError("session not found")
        target.revoke()
        await self._sessions.save(target)
        await self._redis.delete(session_cache_key(session_id))

    async def revoke_other_sessions(self, user_id: UserId, *, current_session_id: UUID) -> int:
        sessions = await self._sessions.list_active_for_user(user_id)
        count = await self._sessions.revoke_all_for_user(user_id, except_session=current_session_id)
        for s in sessions:
            if s.id != current_session_id:
                await self._redis.delete(session_cache_key(s.id))
        return count


class ApiKeyService:
    def __init__(self, *, api_keys: ApiKeyRepository) -> None:
        self._api_keys = api_keys

    async def create(
        self,
        *,
        user_id: UserId,
        organization_id: UUID,
        name: str,
        scopes: list[str],
        expires_in_days: int | None,
    ) -> CreatedApiKeyDTO:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValidationFailed("API key name is required")
        invalid = set(scopes) - API_KEY_SCOPES
        if invalid:
            raise ValidationFailed(f"unknown scopes: {', '.join(sorted(invalid))}")
        expires_at = None
        if expires_in_days is not None:
            if expires_in_days < 1 or expires_in_days > 730:
                raise ValidationFailed("expiry must be between 1 and 730 days")
            expires_at = utc_now() + timedelta(days=expires_in_days)
        full, prefix, key_hash = generate_api_key()
        key = ApiKey(
            id=uuid4(),
            user_id=user_id,
            organization_id=organization_id,
            name=cleaned_name,
            prefix=prefix,
            key_hash=key_hash,
            scopes=sorted(set(scopes)) or ["read"],
            expires_at=expires_at,
        )
        await self._api_keys.add(key)
        return CreatedApiKeyDTO(key=_api_key_dto(key), secret=full)

    async def list(self, organization_id: UUID) -> list[ApiKeyDTO]:
        keys = await self._api_keys.list_for_organization(organization_id)
        return [_api_key_dto(k) for k in keys]

    async def revoke(self, *, organization_id: UUID, key_id: UUID) -> None:
        key = await self._api_keys.get(key_id)
        if key is None or key.organization_id != organization_id:
            raise NotFoundError("API key not found")
        key.revoke()
        await self._api_keys.save(key)


def _api_key_dto(key: ApiKey) -> ApiKeyDTO:
    return ApiKeyDTO(
        id=key.id,
        name=key.name,
        prefix=key.prefix,
        scopes=list(key.scopes),
        created_at=key.created_at,
        expires_at=key.expires_at,
        last_used_at=key.last_used_at,
        revoked_at=key.revoked_at,
    )


def _validate_timezone(tz: str) -> str:
    if tz not in available_timezones():
        raise ValidationFailed("unknown IANA timezone")
    return tz
