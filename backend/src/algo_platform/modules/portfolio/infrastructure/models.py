from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from algo_platform.shared.infrastructure.database import Base


class PortfolioSnapshotModel(Base):
    """Point-in-time equity/cash/PnL record written by the trading engine."""

    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        Index("ix_portfolio_snapshots_account_time", "account_id", "as_of"),
        Index("ix_portfolio_snapshots_org_time", "organization_id", "as_of"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trading_accounts.id", ondelete="CASCADE")
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    equity: Mapped[Decimal]
    cash: Mapped[Decimal]
    realized_pnl: Mapped[Decimal]
    unrealized_pnl: Mapped[Decimal]
    exposure: Mapped[Decimal]
    open_positions: Mapped[int] = mapped_column(default=0)
