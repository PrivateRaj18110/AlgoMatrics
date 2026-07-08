"""Composition-root accessors for per-request resources."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from algo_platform.config import Settings
from algo_platform.shared.application.ports import EmailSender
from algo_platform.shared.infrastructure.encryption import CredentialCipher
from algo_platform.shared.infrastructure.jwt_service import JwtService
from algo_platform.shared.infrastructure.metrics import MetricsRecorder
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_redis(request: Request) -> RedisGateway:
    redis: RedisGateway = request.app.state.redis
    return redis


def get_jwt_service(request: Request) -> JwtService:
    jwt: JwtService = request.app.state.jwt
    return jwt


def get_email_sender(request: Request) -> EmailSender:
    sender: EmailSender = request.app.state.email_sender
    return sender


def get_credential_cipher(request: Request) -> CredentialCipher:
    cipher: CredentialCipher = request.app.state.cipher
    return cipher


def get_metrics(request: Request) -> MetricsRecorder:
    metrics: MetricsRecorder = request.app.state.metrics
    return metrics


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
RedisDep = Annotated[RedisGateway, Depends(get_redis)]
JwtDep = Annotated[JwtService, Depends(get_jwt_service)]
EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]
CipherDep = Annotated[CredentialCipher, Depends(get_credential_cipher)]
MetricsDep = Annotated[MetricsRecorder, Depends(get_metrics)]
