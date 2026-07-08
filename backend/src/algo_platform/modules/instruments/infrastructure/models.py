from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from algo_platform.shared.infrastructure.database import Base


class InstrumentModel(Base):
    """Canonical, broker-neutral instrument master."""

    __tablename__ = "instruments"
    __table_args__ = (Index("ix_instruments_asset_class", "asset_class"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    exchange: Mapped[str] = mapped_column(String(20))
    asset_class: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3))
    tick_size: Mapped[Decimal]
    lot_size: Mapped[Decimal]
    price_precision: Mapped[int] = mapped_column(default=2)
    reference_price: Mapped[Decimal]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VenueInstrumentModel(Base):
    """Broker-specific representation of a canonical instrument."""

    __tablename__ = "venue_instruments"
    __table_args__ = (
        UniqueConstraint("broker_id", "instrument_id"),
        UniqueConstraint("broker_id", "exchange", "venue_symbol"),
        CheckConstraint(
            "tick_size > 0 AND lot_size > 0 AND contract_multiplier > 0",
            name="positive_sizes",
        ),
        Index("ix_venue_instruments_broker_active", "broker_id", "is_active"),
        Index("ix_venue_instruments_instrument", "instrument_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    broker_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("brokers.id", ondelete="CASCADE")
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE")
    )
    venue_symbol: Mapped[str] = mapped_column(String(80))
    exchange: Mapped[str] = mapped_column(String(30))
    instrument_token: Mapped[str | None] = mapped_column(String(120), default=None)
    tick_size: Mapped[Decimal]
    lot_size: Mapped[Decimal]
    contract_multiplier: Mapped[Decimal] = mapped_column(default=Decimal("1"))
    venue_metadata: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
