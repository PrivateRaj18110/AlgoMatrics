from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from algo_platform.shared.infrastructure.database import Base


class OrderModel(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("account_id", "client_order_id"),
        Index("ix_orders_org_created", "organization_id", "created_at"),
        Index(
            "ix_orders_account_open",
            "account_id",
            "created_at",
            postgresql_where=text(
                "status IN ('pending_risk','approved','submitted',"
                "'partially_filled','cancel_pending')"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trading_accounts.id", ondelete="CASCADE")
    )
    strategy_run_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"))
    client_order_id: Mapped[str] = mapped_column(String(64))
    broker_order_id: Mapped[str | None] = mapped_column(String(120), default=None)
    side: Mapped[str] = mapped_column(String(4))
    order_type: Mapped[str] = mapped_column(String(12))
    time_in_force: Mapped[str] = mapped_column(String(4), default="day")
    quantity: Mapped[Decimal]
    limit_price: Mapped[Decimal | None] = mapped_column(default=None)
    stop_price: Mapped[Decimal | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(20))
    filled_quantity: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    average_fill_price: Mapped[Decimal | None] = mapped_column(default=None)
    rejection_reason: Mapped[str | None] = mapped_column(String(300), default=None)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(BigInteger, default=1)


class ExecutionModel(Base):
    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint("broker_execution_id"),
        Index("ix_executions_org_time", "organization_id", "executed_at"),
        Index("ix_executions_order", "order_id"),
        Index("ix_executions_account_time", "account_id", "executed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trading_accounts.id", ondelete="CASCADE")
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"))
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[Decimal]
    price: Mapped[Decimal]
    fee: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    fee_currency: Mapped[str] = mapped_column(String(3), default="INR")
    # Realized PnL delta this fill produced on the position projection
    # (net of fees); denormalized here for win-rate and daily-PnL analytics.
    realized_delta: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    broker_execution_id: Mapped[str] = mapped_column(String(120))


class PositionModel(Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("account_id", "instrument_id"),
        Index("ix_positions_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trading_accounts.id", ondelete="CASCADE")
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"))
    quantity: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    average_price: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    fees_paid: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    last_mark: Mapped[Decimal | None] = mapped_column(default=None)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(BigInteger, default=1)


class WatchlistModel(Base):
    __tablename__ = "watchlists"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(80))
    created_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WatchlistItemModel(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "instrument_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    watchlist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("watchlists.id", ondelete="CASCADE"))
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"))
    sort_order: Mapped[int] = mapped_column(default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
