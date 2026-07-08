"""Authentication use cases: registration, login, MFA challenge, token rotation."""

from __future__ import annotations

import hashlib
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.config import Settings
from algo_platform.modules.identity.application.dto import (
    IssuedTokensDTO,
    LoginResultDTO,
    UserProfileDTO,
)
from algo_platform.modules.identity.domain.repositories import (
    EmailTokenRepository,
    RefreshTokenRepository,
    SessionRepository,
    UserRepository,
)
from algo_platform.modules.identity.domain.users import (
    AuthSession,
    EmailToken,
    EmailTokenPurpose,
    RefreshToken,
    User,
)
from algo_platform.shared.application.ports import EmailMessage, EmailSender
from algo_platform.shared.domain.errors import (
    AuthenticationFailed,
    ConflictError,
    RateLimited,
    ValidationFailed,
)
from algo_platform.shared.domain.types import DomainEvent, TenantId, UserId
from algo_platform.shared.infrastructure.encryption import CredentialCipher, EncryptedSecret
from algo_platform.shared.infrastructure.jwt_service import JwtService
from algo_platform.shared.infrastructure.outbox import enqueue_event
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway
from algo_platform.shared.infrastructure.security import (
    Totp,
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)

logger = structlog.get_logger(__name__)

VERIFY_EMAIL_TTL_SECONDS = 60 * 60 * 24
RESET_PASSWORD_TTL_SECONDS = 60 * 60
MFA_CHALLENGE_TTL_SECONDS = 300
MIN_PASSWORD_LENGTH = 10

# Account lockout: after this many failed password attempts within the window,
# the account is temporarily locked regardless of source IP (defends against
# distributed brute force that IP rate limiting alone would miss).
MAX_FAILED_LOGINS = 8
LOCKOUT_WINDOW_SECONDS = 15 * 60


def _failed_login_key(email: str) -> str:
    return f"login:fail:{email.strip().lower()}"


# Constant-time compensation hash used when the account does not exist.
_DUMMY_HASH = hash_password("dummy-timing-compensation")

SESSION_CACHE_PREFIX = "sess:ok:"
SESSION_CACHE_TTL_SECONDS = 60


def session_cache_key(session_id: UUID) -> str:
    return f"{SESSION_CACHE_PREFIX}{session_id}"


def hash_ip(ip: str | None) -> str:
    return hashlib.sha256((ip or "unknown").encode("utf-8")).hexdigest()[:32]


def user_profile_dto(user: User) -> UserProfileDTO:
    return UserProfileDTO(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        status=user.status.value,
        email_verified=user.is_email_verified,
        mfa_enabled=user.mfa_enabled,
        avatar_url=f"/api/v1/users/{user.id}/avatar" if user.avatar_path else None,
        timezone=user.timezone,
        theme=user.theme.value,
        preferences=dict(user.preferences),
        notification_settings=dict(user.notification_settings),
        is_platform_admin=user.is_platform_admin,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


class AuthService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        users: UserRepository,
        sessions: SessionRepository,
        refresh_tokens: RefreshTokenRepository,
        email_tokens: EmailTokenRepository,
        jwt: JwtService,
        email_sender: EmailSender,
        redis: RedisGateway,
        cipher: CredentialCipher,
        settings: Settings,
    ) -> None:
        self._session = session
        self._users = users
        self._sessions = sessions
        self._refresh_tokens = refresh_tokens
        self._email_tokens = email_tokens
        self._jwt = jwt
        self._email_sender = email_sender
        self._redis = redis
        self._cipher = cipher
        self._settings = settings

    # -- registration -----------------------------------------------------

    async def register(self, *, email: str, password: str, full_name: str) -> User:
        validate_password_strength(password)
        existing = await self._users.get_by_email(email)
        if existing is not None:
            raise ConflictError("an account with this e-mail already exists")
        user = User.register(
            email=email, full_name=full_name, password_hash=hash_password(password)
        )
        await self._users.add(user)
        await enqueue_event(
            self._session,
            event=DomainEvent.new(
                event_type="identity.user_registered.v1",
                aggregate_id=user.id,
                tenant_id=TenantId(user.id),
            ),
            aggregate_type="user",
            payload={"user_id": str(user.id), "email": user.email},
        )
        await self._send_verification_email(user)
        logger.info("auth.user_registered", user_id=str(user.id))
        return user

    async def _send_verification_email(self, user: User) -> None:
        raw = generate_opaque_token(32)
        await self._email_tokens.invalidate_for_user(user.id, EmailTokenPurpose.VERIFY_EMAIL)
        await self._email_tokens.add(
            EmailToken.issue(
                user_id=user.id,
                purpose=EmailTokenPurpose.VERIFY_EMAIL,
                token_hash=hash_token(raw),
                ttl_seconds=VERIFY_EMAIL_TTL_SECONDS,
            )
        )
        link = f"{self._settings.app_base_url}/verify-email?token={raw}"
        await self._email_sender.send(
            EmailMessage(
                to=user.email,
                subject="Verify your Algo Matrics account",
                text=(
                    f"Hi {user.full_name},\n\n"
                    f"Confirm your e-mail address to activate your account:\n{link}\n\n"
                    "The link expires in 24 hours. If you did not create an account, "
                    "ignore this message."
                ),
            )
        )

    async def verify_email(self, raw_token: str) -> User:
        token = await self._email_tokens.get_by_hash(
            hash_token(raw_token), EmailTokenPurpose.VERIFY_EMAIL
        )
        if token is None:
            raise AuthenticationFailed("verification link is invalid")
        token.consume()
        await self._email_tokens.save(token)
        user = await self._users.get(token.user_id)
        if user is None:
            raise AuthenticationFailed("verification link is invalid")
        if not user.is_email_verified:
            user.mark_email_verified()
            await self._users.save(user)
            await enqueue_event(
                self._session,
                event=DomainEvent.new(
                    event_type="identity.email_verified.v1",
                    aggregate_id=user.id,
                    tenant_id=TenantId(user.id),
                ),
                aggregate_type="user",
                payload={"user_id": str(user.id)},
            )
        return user

    async def resend_verification(self, email: str) -> None:
        user = await self._users.get_by_email(email)
        if user is not None and not user.is_email_verified:
            await self._send_verification_email(user)

    # -- login / MFA -------------------------------------------------------

    async def _ensure_not_locked_out(self, email: str) -> None:
        raw = await self._redis.get_str(_failed_login_key(email))
        if raw is not None and int(raw) >= MAX_FAILED_LOGINS:
            logger.warning("auth.account_locked_out", email_hash=hash_token(email))
            raise RateLimited(
                "too many failed attempts; the account is temporarily locked",
                retry_after_seconds=LOCKOUT_WINDOW_SECONDS,
            )

    async def _record_failed_login(self, email: str) -> None:
        try:
            await self._redis.incr_fixed_window(_failed_login_key(email), LOCKOUT_WINDOW_SECONDS)
        except Exception:
            logger.warning("auth.failed_login_tracking_unavailable")

    async def _clear_failed_logins(self, email: str) -> None:
        await self._redis.delete(_failed_login_key(email))

    async def login(
        self, *, email: str, password: str, user_agent: str, ip: str | None
    ) -> LoginResultDTO:
        await self._ensure_not_locked_out(email)
        user = await self._users.get_by_email(email)
        if user is None:
            verify_password(password, _DUMMY_HASH)
            await self._record_failed_login(email)
            raise AuthenticationFailed("invalid e-mail or password")
        if not verify_password(password, user.password_hash):
            await self._record_failed_login(email)
            raise AuthenticationFailed("invalid e-mail or password")
        await self._clear_failed_logins(email)
        user.ensure_can_authenticate()
        if not user.is_email_verified:
            raise AuthenticationFailed(
                "e-mail address is not verified",
                details={"reason": "email_unverified"},
            )
        if user.mfa_enabled:
            challenge = generate_opaque_token(24)
            await self._redis.set_str(
                f"mfa:challenge:{hash_token(challenge)}",
                str(user.id),
                ttl_seconds=MFA_CHALLENGE_TTL_SECONDS,
            )
            return LoginResultDTO(kind="mfa_required", mfa_token=challenge)
        tokens = await self._establish_session(user, user_agent=user_agent, ip=ip)
        return LoginResultDTO(kind="tokens", tokens=tokens)

    async def complete_mfa_login(
        self, *, mfa_token: str, code: str, user_agent: str, ip: str | None
    ) -> IssuedTokensDTO:
        key = f"mfa:challenge:{hash_token(mfa_token)}"
        user_id_raw = await self._redis.get_str(key)
        if user_id_raw is None:
            raise AuthenticationFailed("MFA challenge expired; sign in again")
        user = await self._users.get(UserId(UUID(user_id_raw)))
        if user is None or not user.mfa_enabled:
            raise AuthenticationFailed("MFA challenge is invalid")
        user.ensure_can_authenticate()
        secret = self._decrypt_mfa_secret(user)
        if not Totp(secret).verify(code):
            raise AuthenticationFailed("incorrect authentication code")
        await self._redis.delete(key)
        return await self._establish_session(user, user_agent=user_agent, ip=ip)

    def _decrypt_mfa_secret(self, user: User) -> str:
        if not user.mfa_secret_ciphertext or not user.mfa_secret_wrapped_dek:
            raise AuthenticationFailed("MFA is not configured")
        secret = self._cipher.decrypt(
            EncryptedSecret(
                ciphertext_b64=user.mfa_secret_ciphertext,
                wrapped_dek_b64=user.mfa_secret_wrapped_dek,
                key_version=self._settings.credential_key_version,
            ),
            aad=f"mfa:{user.id}".encode(),
        )
        return secret.decode("utf-8")

    async def _establish_session(
        self, user: User, *, user_agent: str, ip: str | None
    ) -> IssuedTokensDTO:
        auth_session = AuthSession.start(
            user_id=user.id, user_agent=user_agent, ip_hash=hash_ip(ip)
        )
        await self._sessions.add(auth_session)
        raw_refresh = generate_opaque_token()
        refresh = RefreshToken.issue(
            user_id=user.id,
            session_id=auth_session.id,
            token_hash=hash_token(raw_refresh),
            ttl_seconds=self._settings.refresh_token_ttl_seconds,
        )
        await self._refresh_tokens.add(refresh)
        user.record_login()
        await self._users.save(user)
        access = self._jwt.issue(
            user_id=user.id,
            session_id=auth_session.id,
            email=user.email,
            organization_id=None,
            role=None,
            is_platform_admin=user.is_platform_admin,
        )
        await self._redis.set_str(
            session_cache_key(auth_session.id), "1", ttl_seconds=SESSION_CACHE_TTL_SECONDS
        )
        return IssuedTokensDTO(
            access_token=access.token,
            access_expires_at=access.expires_at,
            refresh_token=raw_refresh,
            refresh_expires_at=refresh.expires_at,
            session_id=auth_session.id,
            user=user_profile_dto(user),
        )

    # -- refresh rotation ---------------------------------------------------

    async def refresh(self, *, raw_refresh_token: str) -> IssuedTokensDTO:
        # Rotation is a compare-and-swap operation. Locking the token row makes
        # concurrent refresh requests serialize so only one replacement can
        # be minted and the second request is treated as reuse.
        token = await self._refresh_tokens.get_by_hash_for_update(hash_token(raw_refresh_token))
        if token is None:
            raise AuthenticationFailed("refresh token is invalid")
        if token.was_used:
            # Reuse of a rotated token: assume theft, kill the whole family.
            await self._refresh_tokens.revoke_family(token.family_id)
            auth_session = await self._sessions.get(token.session_id)
            if auth_session is not None and auth_session.is_active:
                auth_session.revoke()
                await self._sessions.save(auth_session)
            await self._redis.delete(session_cache_key(token.session_id))
            logger.warning(
                "auth.refresh_token_reuse_detected",
                user_id=str(token.user_id),
                family_id=str(token.family_id),
            )
            raise AuthenticationFailed("refresh token reuse detected; session revoked")
        if token.is_expired:
            raise AuthenticationFailed("refresh token expired")
        auth_session = await self._sessions.get(token.session_id)
        if auth_session is None or not auth_session.is_active:
            raise AuthenticationFailed("session is no longer active")
        user = await self._users.get(token.user_id)
        if user is None:
            raise AuthenticationFailed("account no longer exists")
        user.ensure_can_authenticate()

        raw_replacement = generate_opaque_token()
        replacement = RefreshToken.issue(
            user_id=user.id,
            session_id=auth_session.id,
            token_hash=hash_token(raw_replacement),
            ttl_seconds=self._settings.refresh_token_ttl_seconds,
            family_id=token.family_id,
        )
        await self._refresh_tokens.add(replacement)
        token.rotate_to(replacement)
        await self._refresh_tokens.save(token)
        auth_session.touch()
        await self._sessions.save(auth_session)

        access = self._jwt.issue(
            user_id=user.id,
            session_id=auth_session.id,
            email=user.email,
            organization_id=None,
            role=None,
            is_platform_admin=user.is_platform_admin,
        )
        return IssuedTokensDTO(
            access_token=access.token,
            access_expires_at=access.expires_at,
            refresh_token=raw_replacement,
            refresh_expires_at=replacement.expires_at,
            session_id=auth_session.id,
            user=user_profile_dto(user),
        )

    async def logout(self, *, session_id: UUID) -> None:
        auth_session = await self._sessions.get(session_id)
        if auth_session is not None and auth_session.is_active:
            auth_session.revoke()
            await self._sessions.save(auth_session)
        await self._refresh_tokens.revoke_for_session(session_id)
        await self._redis.delete(session_cache_key(session_id))

    # -- password reset -----------------------------------------------------

    async def request_password_reset(self, email: str) -> None:
        user = await self._users.get_by_email(email)
        if user is None:
            return
        raw = generate_opaque_token(32)
        await self._email_tokens.invalidate_for_user(user.id, EmailTokenPurpose.RESET_PASSWORD)
        await self._email_tokens.add(
            EmailToken.issue(
                user_id=user.id,
                purpose=EmailTokenPurpose.RESET_PASSWORD,
                token_hash=hash_token(raw),
                ttl_seconds=RESET_PASSWORD_TTL_SECONDS,
            )
        )
        link = f"{self._settings.app_base_url}/reset-password?token={raw}"
        await self._email_sender.send(
            EmailMessage(
                to=user.email,
                subject="Reset your Algo Matrics password",
                text=(
                    f"Hi {user.full_name},\n\n"
                    f"Reset your password using this link (valid for 1 hour):\n{link}\n\n"
                    "If you did not request a reset, you can safely ignore this message."
                ),
            )
        )

    async def reset_password(self, *, raw_token: str, new_password: str) -> None:
        validate_password_strength(new_password)
        token = await self._email_tokens.get_by_hash(
            hash_token(raw_token), EmailTokenPurpose.RESET_PASSWORD
        )
        if token is None:
            raise AuthenticationFailed("reset link is invalid or expired")
        token.consume()
        await self._email_tokens.save(token)
        user = await self._users.get(token.user_id)
        if user is None:
            raise AuthenticationFailed("reset link is invalid or expired")
        user.change_password(hash_password(new_password))
        await self._users.save(user)
        await self._sessions.revoke_all_for_user(user.id, except_session=None)
        await self._email_sender.send(
            EmailMessage(
                to=user.email,
                subject="Your Algo Matrics password was changed",
                text=(
                    f"Hi {user.full_name},\n\n"
                    "Your password was just changed and all active sessions were signed "
                    "out. If this was not you, reset your password immediately and "
                    "contact support."
                ),
            )
        )

    # -- websocket tickets ----------------------------------------------------

    async def issue_ws_ticket(self, *, user_id: UserId, organization_id: UUID) -> str:
        ticket = generate_opaque_token(24)
        await self._redis.set_json(
            f"ws:ticket:{hash_token(ticket)}",
            {"user_id": str(user_id), "organization_id": str(organization_id)},
            ttl_seconds=self._settings.ws_ticket_ttl_seconds,
        )
        return ticket


def validate_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationFailed(f"password must be at least {MIN_PASSWORD_LENGTH} characters long")
    if password.lower() == password or password.upper() == password:
        raise ValidationFailed("password must mix upper- and lower-case characters")
    if not any(ch.isdigit() for ch in password):
        raise ValidationFailed("password must contain at least one digit")
