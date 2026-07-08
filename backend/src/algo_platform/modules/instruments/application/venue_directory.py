"""Venue-instrument mapping use cases and live-routing read facade."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.instruments.infrastructure.models import (
    InstrumentModel,
    VenueInstrumentModel,
)
from algo_platform.shared.domain.errors import ConflictError, NotFoundError, ValidationFailed
from algo_platform.shared.domain.types import utc_now


@dataclass(frozen=True, slots=True)
class VenueInstrumentDTO:
    id: UUID
    broker_id: UUID
    instrument_id: UUID
    canonical_symbol: str
    venue_symbol: str
    exchange: str
    instrument_token: str | None
    tick_size: Decimal
    lot_size: Decimal
    contract_multiplier: Decimal
    venue_metadata: dict[str, str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class VenueInstrumentDirectory:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(self, *, broker_id: UUID, instrument_id: UUID) -> VenueInstrumentDTO:
        statement = (
            select(VenueInstrumentModel, InstrumentModel)
            .join(InstrumentModel, InstrumentModel.id == VenueInstrumentModel.instrument_id)
            .where(
                VenueInstrumentModel.broker_id == broker_id,
                VenueInstrumentModel.instrument_id == instrument_id,
                VenueInstrumentModel.is_active,
                InstrumentModel.is_active,
            )
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            raise NotFoundError(
                "instrument is not mapped for this broker",
                details={
                    "broker_id": str(broker_id),
                    "instrument_id": str(instrument_id),
                },
            )
        return self._dto(*row)

    async def list(
        self,
        *,
        broker_id: UUID | None = None,
        instrument_id: UUID | None = None,
        include_inactive: bool = False,
    ) -> list[VenueInstrumentDTO]:
        statement = (
            select(VenueInstrumentModel, InstrumentModel)
            .join(InstrumentModel, InstrumentModel.id == VenueInstrumentModel.instrument_id)
        )
        if broker_id is not None:
            statement = statement.where(VenueInstrumentModel.broker_id == broker_id)
        if instrument_id is not None:
            statement = statement.where(VenueInstrumentModel.instrument_id == instrument_id)
        if not include_inactive:
            statement = statement.where(VenueInstrumentModel.is_active)
        statement = statement.order_by(VenueInstrumentModel.broker_id, InstrumentModel.symbol)
        rows = (await self._session.execute(statement)).all()
        return [self._dto(*row) for row in rows]

    async def create(
        self,
        *,
        broker_id: UUID,
        instrument_id: UUID,
        venue_symbol: str,
        exchange: str,
        instrument_token: str | None,
        tick_size: Decimal | None,
        lot_size: Decimal | None,
        contract_multiplier: Decimal,
        venue_metadata: dict[str, str],
    ) -> VenueInstrumentDTO:
        instrument = await self._session.get(InstrumentModel, instrument_id)
        if instrument is None:
            raise NotFoundError("instrument not found")
        existing = await self._session.execute(
            select(VenueInstrumentModel.id).where(
                VenueInstrumentModel.broker_id == broker_id,
                VenueInstrumentModel.instrument_id == instrument_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError("this instrument already has a mapping for the broker")
        symbol = self._clean_required(venue_symbol, "venue symbol", 80).upper()
        venue_exchange = self._clean_required(exchange, "exchange", 30).upper()
        duplicate_symbol = await self._session.execute(
            select(VenueInstrumentModel.id).where(
                VenueInstrumentModel.broker_id == broker_id,
                VenueInstrumentModel.exchange == venue_exchange,
                VenueInstrumentModel.venue_symbol == symbol,
            )
        )
        if duplicate_symbol.scalar_one_or_none() is not None:
            raise ConflictError("this venue symbol is already mapped for the broker")
        self._validate_positive("tick size", tick_size or instrument.tick_size)
        self._validate_positive("lot size", lot_size or instrument.lot_size)
        self._validate_positive("contract multiplier", contract_multiplier)
        now = utc_now()
        model = VenueInstrumentModel(
            id=uuid4(),
            broker_id=broker_id,
            instrument_id=instrument_id,
            venue_symbol=symbol,
            exchange=venue_exchange,
            instrument_token=self._clean_optional(instrument_token, 120),
            tick_size=tick_size or instrument.tick_size,
            lot_size=lot_size or instrument.lot_size,
            contract_multiplier=contract_multiplier,
            venue_metadata=self._clean_metadata(venue_metadata),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        await self._session.flush()
        return self._dto(model, instrument)

    async def update(
        self,
        mapping_id: UUID,
        *,
        venue_symbol: str | None = None,
        exchange: str | None = None,
        instrument_token: str | None = None,
        tick_size: Decimal | None = None,
        lot_size: Decimal | None = None,
        contract_multiplier: Decimal | None = None,
        venue_metadata: dict[str, str] | None = None,
        is_active: bool | None = None,
    ) -> VenueInstrumentDTO:
        model = await self._session.get(VenueInstrumentModel, mapping_id)
        if model is None:
            raise NotFoundError("venue instrument mapping not found")
        if venue_symbol is not None:
            model.venue_symbol = self._clean_required(venue_symbol, "venue symbol", 80).upper()
        if exchange is not None:
            model.exchange = self._clean_required(exchange, "exchange", 30).upper()
        if instrument_token is not None:
            model.instrument_token = self._clean_optional(instrument_token, 120)
        if tick_size is not None:
            self._validate_positive("tick size", tick_size)
            model.tick_size = tick_size
        if lot_size is not None:
            self._validate_positive("lot size", lot_size)
            model.lot_size = lot_size
        if contract_multiplier is not None:
            self._validate_positive("contract multiplier", contract_multiplier)
            model.contract_multiplier = contract_multiplier
        if venue_metadata is not None:
            model.venue_metadata = self._clean_metadata(venue_metadata)
        if is_active is not None:
            model.is_active = is_active
        model.updated_at = utc_now()
        await self._session.flush()
        instrument = await self._session.get(InstrumentModel, model.instrument_id)
        if instrument is None:
            raise NotFoundError("mapping references a missing instrument")
        return self._dto(model, instrument)

    @staticmethod
    def _dto(
        model: VenueInstrumentModel,
        instrument: InstrumentModel,
    ) -> VenueInstrumentDTO:
        return VenueInstrumentDTO(
            id=model.id,
            broker_id=model.broker_id,
            instrument_id=model.instrument_id,
            canonical_symbol=instrument.symbol,
            venue_symbol=model.venue_symbol,
            exchange=model.exchange,
            instrument_token=model.instrument_token,
            tick_size=model.tick_size,
            lot_size=model.lot_size,
            contract_multiplier=model.contract_multiplier,
            venue_metadata=dict(model.venue_metadata),
            is_active=model.is_active,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _clean_required(value: str, label: str, maximum: int) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValidationFailed(f"{label} is required")
        if len(cleaned) > maximum:
            raise ValidationFailed(f"{label} must be {maximum} characters or fewer")
        return cleaned

    @staticmethod
    def _clean_optional(value: str | None, maximum: int) -> str | None:
        cleaned = (value or "").strip()
        if not cleaned:
            return None
        if len(cleaned) > maximum:
            raise ValidationFailed(f"instrument token must be {maximum} characters or fewer")
        return cleaned

    @staticmethod
    def _clean_metadata(value: dict[str, str]) -> dict[str, str]:
        if len(value) > 20:
            raise ValidationFailed("venue metadata supports at most 20 entries")
        cleaned: dict[str, str] = {}
        for key, item in value.items():
            clean_key = str(key).strip()
            clean_value = str(item).strip()
            if not clean_key or len(clean_key) > 60 or len(clean_value) > 300:
                raise ValidationFailed("venue metadata keys or values are invalid")
            cleaned[clean_key] = clean_value
        return cleaned

    @staticmethod
    def _validate_positive(label: str, value: Decimal) -> None:
        if not value.is_finite() or value <= 0:
            raise ValidationFailed(f"{label} must be a positive finite number")
