from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import NewType
from uuid import UUID, uuid4

TenantId = NewType("TenantId", UUID)
UserId = NewType("UserId", UUID)
AccountId = NewType("AccountId", UUID)
StrategyRunId = NewType("StrategyRunId", UUID)
OrderId = NewType("OrderId", UUID)


def utc_now() -> datetime:
    return datetime.now(UTC)


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if len(self.currency) != 3:
            raise ValueError("currency must be an ISO-4217 three-letter code")


@dataclass(frozen=True, slots=True)
class DomainEvent:
    event_id: UUID
    event_type: str
    aggregate_id: UUID
    tenant_id: TenantId
    occurred_at: datetime
    schema_version: int = 1

    @classmethod
    def new(
        cls,
        *,
        event_type: str,
        aggregate_id: UUID,
        tenant_id: TenantId,
    ) -> DomainEvent:
        return cls(
            event_id=uuid4(),
            event_type=event_type,
            aggregate_id=aggregate_id,
            tenant_id=tenant_id,
            occurred_at=utc_now(),
        )
