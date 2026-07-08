from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from algo_platform.shared.infrastructure.database import Base


class RiskLimitsModel(Base):
    __tablename__ = "risk_limits"
    __table_args__ = (
        UniqueConstraint("organization_id", "account_id"),
        Index("ix_risk_limits_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    max_order_quantity: Mapped[Decimal]
    max_order_value: Mapped[Decimal]
    max_daily_loss: Mapped[Decimal]
    max_open_positions: Mapped[int]
    max_exposure_value: Mapped[Decimal]
    max_drawdown_pct: Mapped[Decimal]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class KillSwitchModel(Base):
    __tablename__ = "kill_switches"
    __table_args__ = (Index("ix_kill_switches_org_scope", "organization_id", "scope"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    scope: Mapped[str] = mapped_column(String(20))
    scope_ref: Mapped[str] = mapped_column(String(64), default="")
    reason: Mapped[str] = mapped_column(String(300))
    engaged_by: Mapped[uuid.UUID]
    engaged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(default=None)
    released_by: Mapped[uuid.UUID | None] = mapped_column(default=None)


class RiskDecisionModel(Base):
    __tablename__ = "risk_decisions"
    __table_args__ = (Index("ix_risk_decisions_org_time", "organization_id", "decided_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    order_id: Mapped[uuid.UUID]
    result: Mapped[str] = mapped_column(String(10))
    reason_codes: Mapped[list[str]] = mapped_column(default=list)
    inputs: Mapped[dict[str, Any]] = mapped_column(default=dict)
    policy_version: Mapped[int] = mapped_column(default=1)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RiskEventModel(Base):
    """Continuous-risk violations (daily loss, drawdown, exposure breaches)."""

    __tablename__ = "risk_events"
    __table_args__ = (Index("ix_risk_events_org_time", "organization_id", "occurred_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    strategy_run_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    event_type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10), default="warning")
    message: Mapped[str] = mapped_column(String(500))
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
