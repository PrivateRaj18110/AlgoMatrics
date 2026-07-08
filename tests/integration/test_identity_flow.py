"""Integration: registration → login → refresh rotation → reuse detection."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from algo_platform.config import Settings
from algo_platform.modules.identity.application.auth_service import AuthService
from algo_platform.modules.identity.infrastructure.repositories import (
    SqlEmailTokenRepository,
    SqlRefreshTokenRepository,
    SqlSessionRepository,
    SqlUserRepository,
)
from algo_platform.shared.application.ports import EmailMessage
from algo_platform.shared.domain.errors import AuthenticationFailed, ConflictError
from algo_platform.shared.infrastructure.encryption import CredentialCipher
from algo_platform.shared.infrastructure.jwt_service import JwtService
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway

pytestmark = pytest.mark.integration


class CapturingEmailSender:
    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.messages.append(message)


def build_service(
    session: AsyncSession,
    redis: RedisGateway,
    keypair: tuple[str, str],
    kek_b64: str,
    email_sender: CapturingEmailSender,
) -> AuthService:
    private_pem, public_pem = keypair
    settings = Settings(
        database_url="postgresql+asyncpg://x/y",
        redis_url="redis://x",
        jwt_private_key_pem=private_pem,
        jwt_public_key_pem=public_pem,
        broker_credential_kek_b64=kek_b64,
    )  # type: ignore[call-arg]
    jwt = JwtService(
        private_key_pem=private_pem,
        public_key_pem=public_pem,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        access_ttl_seconds=900,
    )
    return AuthService(
        session=session,
        users=SqlUserRepository(session),
        sessions=SqlSessionRepository(session),
        refresh_tokens=SqlRefreshTokenRepository(session),
        email_tokens=SqlEmailTokenRepository(session),
        jwt=jwt,
        email_sender=email_sender,
        redis=redis,
        cipher=CredentialCipher.from_base64(kek_b64),
        settings=settings,
    )


async def test_register_verify_login_and_refresh_rotation(
    session_factory: async_sessionmaker[AsyncSession],
    _redis_url: str,
    rsa_keypair: tuple[str, str],
    kek_b64: str,
) -> None:
    redis = RedisGateway.from_url(_redis_url)
    email_sender = CapturingEmailSender()

    async with session_factory() as session:
        service = build_service(session, redis, rsa_keypair, kek_b64, email_sender)
        user = await service.register(
            email="trader@example.com", password="Str0ngPass99", full_name="Trader One"
        )
        await session.commit()

    # A verification e-mail was captured; extract the token from its link.
    assert email_sender.messages
    verify_link = email_sender.messages[0].text
    token = verify_link.split("token=")[1].split()[0]

    async with session_factory() as session:
        service = build_service(session, redis, rsa_keypair, kek_b64, email_sender)
        await service.verify_email(token)
        await session.commit()

    async with session_factory() as session:
        service = build_service(session, redis, rsa_keypair, kek_b64, email_sender)
        result = await service.login(
            email="trader@example.com",
            password="Str0ngPass99",
            user_agent="pytest",
            ip="127.0.0.1",
        )
        await session.commit()
    assert result.kind == "tokens"
    assert result.tokens is not None
    first_refresh = result.tokens.refresh_token

    # Rotate the refresh token.
    async with session_factory() as session:
        service = build_service(session, redis, rsa_keypair, kek_b64, email_sender)
        rotated = await service.refresh(raw_refresh_token=first_refresh)
        await session.commit()
    assert rotated.refresh_token != first_refresh

    # Reusing the original (now-rotated) token must revoke the family.
    async with session_factory() as session:
        service = build_service(session, redis, rsa_keypair, kek_b64, email_sender)
        with pytest.raises(AuthenticationFailed, match="reuse detected"):
            await service.refresh(raw_refresh_token=first_refresh)
        await session.commit()

    # The rotated token is now revoked too (family killed).
    async with session_factory() as session:
        service = build_service(session, redis, rsa_keypair, kek_b64, email_sender)
        with pytest.raises(AuthenticationFailed):
            await service.refresh(raw_refresh_token=rotated.refresh_token)

    await redis.close()

    _ = user  # silence unused


async def test_duplicate_registration_rejected(
    session_factory: async_sessionmaker[AsyncSession],
    _redis_url: str,
    rsa_keypair: tuple[str, str],
    kek_b64: str,
) -> None:
    redis = RedisGateway.from_url(_redis_url)
    email_sender = CapturingEmailSender()
    async with session_factory() as session:
        service = build_service(session, redis, rsa_keypair, kek_b64, email_sender)
        await service.register(email="dupe@example.com", password="Str0ngPass99", full_name="Dupe")
        await session.commit()
    async with session_factory() as session:
        service = build_service(session, redis, rsa_keypair, kek_b64, email_sender)
        with pytest.raises(ConflictError):
            await service.register(
                email="dupe@example.com", password="Str0ngPass99", full_name="Dupe"
            )
    await redis.close()
