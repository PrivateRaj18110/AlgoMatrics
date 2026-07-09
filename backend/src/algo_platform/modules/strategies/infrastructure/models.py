from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from algo_platform.shared.infrastructure.database import Base


class StrategyModel(Base):
    __tablename__ = "strategies"
    __table_args__ = (Index("ix_strategies_org", "organization_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list[str]] = mapped_column(default=list)
    status: Mapped[str] = mapped_column(String(15), default="draft")
    created_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)
    version: Mapped[int] = mapped_column(BigInteger, default=1)


class StrategyVersionModel(Base):
    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version"),
        Index("ix_strategy_versions_strategy", "strategy_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    strategy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"))
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    version: Mapped[int]
    source: Mapped[str] = mapped_column(String(10))
    entry_point: Mapped[str] = mapped_column(String(300))
    artifact_path: Mapped[str | None] = mapped_column(String(300), default=None)
    checksum: Mapped[str] = mapped_column(String(64))
    manifest: Mapped[dict[str, Any]] = mapped_column(default=dict)
    approved_for_live: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StrategyRunModel(Base):
    __tablename__ = "strategy_runs"
    __table_args__ = (
        Index("ix_strategy_runs_org_state", "organization_id", "state"),
        Index("ix_strategy_runs_account", "account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"))
    strategy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="CASCADE")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trading_accounts.id", ondelete="CASCADE")
    )
    mode: Mapped[str] = mapped_column(String(10))
    state: Mapped[str] = mapped_column(String(15))
    parameters: Mapped[dict[str, Any]] = mapped_column(default=dict)
    instrument_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    timeframe: Mapped[str] = mapped_column(String(6), default="1m")
    created_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    stopped_at: Mapped[datetime | None] = mapped_column(default=None)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(String(500), default=None)
    stats: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(BigInteger, default=1)


class StrategyLogModel(Base):
    __tablename__ = "strategy_logs"
    __table_args__ = (Index("ix_strategy_logs_run_time", "run_id", "logged_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategy_runs.id", ondelete="CASCADE"))
    organization_id: Mapped[uuid.UUID]
    level: Mapped[str] = mapped_column(String(10), default="info")
    message: Mapped[str] = mapped_column(String(1000))
    context: Mapped[dict[str, Any]] = mapped_column(default=dict)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BacktestRunModel(Base):
    __tablename__ = "backtest_runs"
    __table_args__ = (Index("ix_backtest_runs_org_time", "organization_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID]
    signal_type: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
