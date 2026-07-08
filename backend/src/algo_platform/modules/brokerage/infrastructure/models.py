from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
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


class BrokerModel(Base):
    __tablename__ = "brokers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(500), default="")
    credential_fields: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    capabilities: Mapped[dict[str, Any]] = mapped_column(default=dict)
    supports_paper: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_live: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BrokerConnectionModel(Base):
    __tablename__ = "broker_connections"
    __table_args__ = (
        Index("ix_broker_connections_org", "organization_id"),
        UniqueConstraint("organization_id", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    broker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brokers.id"))
    broker_code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    credential_ciphertext: Mapped[str] = mapped_column(Text)
    credential_wrapped_dek: Mapped[str] = mapped_column(Text)
    key_version: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(15), default="pending")
    last_verified_at: Mapped[datetime | None] = mapped_column(default=None)
    failure_reason: Mapped[str | None] = mapped_column(String(300), default=None)
    created_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)
    version: Mapped[int] = mapped_column(BigInteger, default=1)


class TradingAccountModel(Base):
    __tablename__ = "trading_accounts"
    __table_args__ = (
        Index("ix_trading_accounts_org", "organization_id"),
        Index("ix_trading_accounts_connection", "connection_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("broker_connections.id", ondelete="CASCADE")
    )
    external_account_id: Mapped[str] = mapped_column(String(120), default="")
    name: Mapped[str] = mapped_column(String(120))
    mode: Mapped[str] = mapped_column(String(10))
    base_currency: Mapped[str] = mapped_column(String(3))
    cash_balance: Mapped[Decimal]
    starting_balance: Mapped[Decimal]
    equity: Mapped[Decimal]
    status: Mapped[str] = mapped_column(String(10), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(BigInteger, default=1)
