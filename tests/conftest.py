"""Shared integration/e2e fixtures: real PostgreSQL + Redis via testcontainers.

Skipped automatically when Docker is unavailable so the default unit run stays
hermetic. The full schema is created from the declarative metadata (mirroring
the baseline migration) and reference data is seeded before each session.
"""

from __future__ import annotations

import base64
import secrets
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

try:
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer

    _HAVE_TESTCONTAINERS = True
except Exception:
    _HAVE_TESTCONTAINERS = False


def _docker_available() -> bool:
    if not _HAVE_TESTCONTAINERS:
        return False
    import shutil

    return shutil.which("docker") is not None


requires_infra = pytest.mark.skipif(
    not _docker_available(), reason="Docker/testcontainers not available"
)


@pytest.fixture(scope="session")
def _postgres_url() -> AsyncIterator[str]:
    if not _docker_available():
        pytest.skip("Docker not available")
    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session")
def _redis_url() -> AsyncIterator[str]:
    if not _docker_available():
        pytest.skip("Docker not available")
    with RedisContainer("redis:7-alpine") as redis:
        host = redis.get_container_host_ip()
        port = redis.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


@pytest.fixture(scope="session")
def rsa_keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private_pem, public_pem


@pytest.fixture(scope="session")
def kek_b64() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode()


@pytest_asyncio.fixture
async def session_factory(_postgres_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # Import every model so the metadata is complete before create_all.
    import algo_platform.modules.audit.infrastructure.models
    import algo_platform.modules.billing.infrastructure.models
    import algo_platform.modules.brokerage.infrastructure.models
    import algo_platform.modules.identity.infrastructure.models
    import algo_platform.modules.instruments.infrastructure.models
    import algo_platform.modules.notifications.infrastructure.models
    import algo_platform.modules.organizations.infrastructure.models
    import algo_platform.modules.portfolio.infrastructure.models
    import algo_platform.modules.risk.infrastructure.models
    import algo_platform.modules.strategies.infrastructure.models
    import algo_platform.modules.trading.infrastructure.models
    import algo_platform.shared.infrastructure.outbox  # noqa: F401
    from algo_platform.shared.infrastructure.database import Base, create_engine

    engine = create_engine(_postgres_url, pool_size=5)
    async with engine.begin() as connection:
        await connection.execute(text("CREATE SEQUENCE IF NOT EXISTS invoice_number_seq START 1"))
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.execute(text("DROP SEQUENCE IF EXISTS invoice_number_seq"))
        await engine.dispose()


@pytest_asyncio.fixture
async def seeded_plans(session_factory: async_sessionmaker[AsyncSession]) -> None:
    import uuid

    from algo_platform.modules.billing.infrastructure.models import PlanModel
    from algo_platform.shared.domain.types import utc_now

    async with session_factory() as session:
        session.add(
            PlanModel(
                id=uuid.uuid4(),
                code="free",
                name="Free",
                description="",
                price_monthly=Decimal("0"),
                price_yearly=Decimal("0"),
                currency="INR",
                features=[],
                limits={
                    "max_broker_connections": 1,
                    "max_active_strategies": 1,
                    "max_orders_per_day": 20,
                    "max_members": 1,
                    "max_watchlists": 3,
                    "api_access": False,
                    "live_trading": False,
                },
                trial_days=0,
                is_active=True,
                sort_order=0,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
        await session.commit()
