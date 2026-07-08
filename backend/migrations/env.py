"""Alembic async environment. Metadata is the shared declarative Base."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import every module that declares tables so Base.metadata is complete.
import algo_platform.modules.audit.infrastructure.models
import algo_platform.modules.billing.infrastructure.models
import algo_platform.modules.brokerage.infrastructure.models
import algo_platform.modules.feature_flags.infrastructure.models
import algo_platform.modules.identity.infrastructure.models
import algo_platform.modules.instruments.infrastructure.models
import algo_platform.modules.notifications.infrastructure.models
import algo_platform.modules.organizations.infrastructure.models
import algo_platform.modules.portfolio.infrastructure.models
import algo_platform.modules.risk.infrastructure.models
import algo_platform.modules.strategies.infrastructure.models
import algo_platform.modules.trading.infrastructure.models
import algo_platform.shared.infrastructure.email_outbox
import algo_platform.shared.infrastructure.outbox  # noqa: F401
from algo_platform.shared.infrastructure.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
