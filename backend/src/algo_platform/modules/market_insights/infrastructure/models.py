from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from algo_platform.shared.infrastructure.database import Base


class MarketSnapshotModel(Base):
    """One stored NSE daily snapshot (pre-open auction, FII/DII flows, ...).

    Stored verbatim so the page can be re-derived later and history kept; one
    row per kind per trading date.
    """

    __tablename__ = "market_snapshots"
    __table_args__ = (UniqueConstraint("kind", "trade_date"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(40))
    trade_date: Mapped[date] = mapped_column(Date)
    fetched_at: Mapped[datetime]
    # dict (pre-open) or list (FII/DII): stored as the source sent it.
    payload: Mapped[Any] = mapped_column(JSONB)
