"""Read facade other contexts use to resolve instrument metadata."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.instruments.infrastructure.models import InstrumentModel


@dataclass(frozen=True, slots=True)
class InstrumentSummary:
    id: UUID
    symbol: str
    name: str
    exchange: str
    asset_class: str
    currency: str
    tick_size: Decimal
    lot_size: Decimal
    reference_price: Decimal


def _summary(model: InstrumentModel) -> InstrumentSummary:
    return InstrumentSummary(
        id=model.id,
        symbol=model.symbol,
        name=model.name,
        exchange=model.exchange,
        asset_class=model.asset_class,
        currency=model.currency,
        tick_size=model.tick_size,
        lot_size=model.lot_size,
        reference_price=model.reference_price,
    )


class InstrumentDirectory:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, instrument_id: UUID) -> InstrumentSummary | None:
        model = await self._session.get(InstrumentModel, instrument_id)
        if model is None or not model.is_active:
            return None
        return _summary(model)

    async def get_map(self, instrument_ids: list[UUID]) -> dict[UUID, InstrumentSummary]:
        if not instrument_ids:
            return {}
        result = await self._session.execute(
            select(InstrumentModel).where(InstrumentModel.id.in_(set(instrument_ids)))
        )
        return {m.id: _summary(m) for m in result.scalars().all()}

    async def list_active(self) -> list[InstrumentSummary]:
        result = await self._session.execute(
            select(InstrumentModel)
            .where(InstrumentModel.is_active)
            .order_by(InstrumentModel.symbol)
        )
        return [_summary(m) for m in result.scalars().all()]

    async def get_by_symbol(self, symbol: str) -> InstrumentSummary | None:
        result = await self._session.execute(
            select(InstrumentModel).where(
                InstrumentModel.symbol == symbol.strip().upper(),
                InstrumentModel.is_active,
            )
        )
        model = result.scalar_one_or_none()
        return _summary(model) if model else None
