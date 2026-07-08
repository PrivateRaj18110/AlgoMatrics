from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select

from algo_platform.api.dependencies.auth import PlatformAdminDep
from algo_platform.api.dependencies.core import RedisDep, SessionDep
from algo_platform.api.dependencies.tenant import TenantContext, require_permission
from algo_platform.modules.audit.application.service import AuditService
from algo_platform.modules.brokerage.application.directory import BrokerDirectory
from algo_platform.modules.instruments.application.venue_directory import (
    VenueInstrumentDirectory,
)
from algo_platform.modules.instruments.infrastructure.models import InstrumentModel
from algo_platform.modules.organizations.domain.roles import Permission
from algo_platform.shared.domain.errors import NotFoundError

router = APIRouter(prefix="/market-data", tags=["market-data"])
admin_router = APIRouter(prefix="/admin/venue-instruments", tags=["admin-venue-instruments"])

TradingViewTenant = Annotated[TenantContext, Depends(require_permission(Permission.TRADING_VIEW))]

LAST_PRICES_KEY = "md:last"
CANDLES_KEY_PREFIX = "md:candles"


class InstrumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    symbol: str
    name: str
    exchange: str
    asset_class: str
    currency: str
    tick_size: Decimal
    lot_size: Decimal
    price_precision: int
    is_active: bool


class QuoteResponse(BaseModel):
    instrument_id: UUID
    symbol: str
    bid: Decimal | None = None
    ask: Decimal | None = None
    last: Decimal | None = None
    change_pct: Decimal | None = None
    timestamp: str | None = None


class ScannerRow(BaseModel):
    instrument_id: UUID
    symbol: str
    name: str
    asset_class: str
    last: Decimal | None
    change_pct: Decimal | None


class CandleResponse(BaseModel):
    timestamp: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class VenueInstrumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class CreateVenueInstrumentRequest(BaseModel):
    broker_id: UUID
    instrument_id: UUID
    venue_symbol: str = Field(min_length=1, max_length=80)
    exchange: str = Field(min_length=1, max_length=30)
    instrument_token: str | None = Field(default=None, max_length=120)
    tick_size: Decimal | None = Field(default=None, gt=0)
    lot_size: Decimal | None = Field(default=None, gt=0)
    contract_multiplier: Decimal = Field(default=Decimal("1"), gt=0)
    venue_metadata: dict[str, str] = Field(default_factory=dict)


class UpdateVenueInstrumentRequest(BaseModel):
    venue_symbol: str | None = Field(default=None, min_length=1, max_length=80)
    exchange: str | None = Field(default=None, min_length=1, max_length=30)
    instrument_token: str | None = Field(default=None, max_length=120)
    tick_size: Decimal | None = Field(default=None, gt=0)
    lot_size: Decimal | None = Field(default=None, gt=0)
    contract_multiplier: Decimal | None = Field(default=None, gt=0)
    venue_metadata: dict[str, str] | None = None
    is_active: bool | None = None


@router.get("/instruments", response_model=list[InstrumentResponse])
async def list_instruments(
    tenant: TradingViewTenant,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=60)] = None,
    asset_class: Annotated[str | None, Query(max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[InstrumentResponse]:
    stmt = select(InstrumentModel).where(InstrumentModel.is_active)
    if q:
        pattern = f"%{q.strip().upper()}%"
        stmt = stmt.where(
            or_(
                InstrumentModel.symbol.ilike(pattern),
                InstrumentModel.name.ilike(pattern),
            )
        )
    if asset_class:
        stmt = stmt.where(InstrumentModel.asset_class == asset_class.strip().lower())
    stmt = stmt.order_by(InstrumentModel.symbol).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [InstrumentResponse.model_validate(r) for r in rows]


@router.get("/quotes", response_model=list[QuoteResponse])
async def get_quotes(
    tenant: TradingViewTenant,
    session: SessionDep,
    redis: RedisDep,
    instrument_ids: Annotated[str | None, Query(description="comma-separated UUIDs")] = None,
) -> list[QuoteResponse]:
    stmt = select(InstrumentModel).where(InstrumentModel.is_active)
    if instrument_ids:
        try:
            wanted = [UUID(part) for part in instrument_ids.split(",") if part.strip()]
        except ValueError:
            wanted = []
        if wanted:
            stmt = stmt.where(InstrumentModel.id.in_(wanted))
    rows = (await session.execute(stmt)).scalars().all()
    quotes_raw = await redis.hgetall_json(LAST_PRICES_KEY)
    quotes: list[QuoteResponse] = []
    for row in rows:
        tick: dict[str, Any] | None = quotes_raw.get(str(row.id))
        if tick is None:
            quotes.append(QuoteResponse(instrument_id=row.id, symbol=row.symbol))
            continue
        quotes.append(
            QuoteResponse(
                instrument_id=row.id,
                symbol=row.symbol,
                bid=Decimal(str(tick["bid"])) if tick.get("bid") else None,
                ask=Decimal(str(tick["ask"])) if tick.get("ask") else None,
                last=Decimal(str(tick["last"])) if tick.get("last") else None,
                change_pct=(Decimal(str(tick["change_pct"])) if tick.get("change_pct") else None),
                timestamp=str(tick.get("timestamp")) if tick.get("timestamp") else None,
            )
        )
    return quotes


@router.get("/scanner", response_model=list[ScannerRow])
async def scanner(
    tenant: TradingViewTenant,
    session: SessionDep,
    redis: RedisDep,
    asset_class: Annotated[str | None, Query(max_length=20)] = None,
    sort: Annotated[str, Query(pattern="^(gainers|losers|active)$")] = "gainers",
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[ScannerRow]:
    """Top movers derived from the live quote cache (market scanner)."""
    stmt = select(InstrumentModel).where(InstrumentModel.is_active)
    if asset_class:
        stmt = stmt.where(InstrumentModel.asset_class == asset_class.strip().lower())
    rows = (await session.execute(stmt)).scalars().all()
    quotes_raw = await redis.hgetall_json(LAST_PRICES_KEY)

    scanned: list[ScannerRow] = []
    for row in rows:
        tick: dict[str, Any] | None = quotes_raw.get(str(row.id))
        change = (
            Decimal(str(tick["change_pct"]))
            if tick and tick.get("change_pct") is not None
            else None
        )
        scanned.append(
            ScannerRow(
                instrument_id=row.id,
                symbol=row.symbol,
                name=row.name,
                asset_class=row.asset_class,
                last=Decimal(str(tick["last"])) if tick and tick.get("last") else None,
                change_pct=change,
            )
        )

    def key(entry: ScannerRow) -> Decimal:
        return entry.change_pct if entry.change_pct is not None else Decimal("0")

    if sort == "gainers":
        scanned.sort(key=key, reverse=True)
    elif sort == "losers":
        scanned.sort(key=key)
    else:  # active = largest absolute move
        scanned.sort(key=lambda entry: abs(key(entry)), reverse=True)
    return scanned[:limit]


@router.get("/candles/{instrument_id}", response_model=list[CandleResponse])
async def get_candles(
    instrument_id: UUID,
    tenant: TradingViewTenant,
    session: SessionDep,
    redis: RedisDep,
    timeframe: Annotated[str, Query(pattern="^(1m|5m|15m|1h)$")] = "1m",
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[CandleResponse]:
    instrument = await session.get(InstrumentModel, instrument_id)
    if instrument is None or not instrument.is_active:
        raise NotFoundError("instrument not found")
    raw = await redis.get_json(f"{CANDLES_KEY_PREFIX}:{instrument_id}:{timeframe}")
    if raw is None:
        return []
    candles_list = raw.get("candles", [])
    result: list[CandleResponse] = []
    for item in candles_list[-limit:]:
        result.append(
            CandleResponse(
                timestamp=str(item["timestamp"]),
                open=Decimal(str(item["open"])),
                high=Decimal(str(item["high"])),
                low=Decimal(str(item["low"])),
                close=Decimal(str(item["close"])),
                volume=Decimal(str(item["volume"])),
            )
        )
    return result


@router.get(
    "/instruments/{instrument_id}/venues",
    response_model=list[VenueInstrumentResponse],
)
async def list_instrument_venues(
    instrument_id: UUID,
    tenant: TradingViewTenant,
    session: SessionDep,
) -> list[VenueInstrumentResponse]:
    mappings = await VenueInstrumentDirectory(session).list(instrument_id=instrument_id)
    return [VenueInstrumentResponse.model_validate(mapping) for mapping in mappings]


@admin_router.get("", response_model=list[VenueInstrumentResponse])
async def list_venue_instruments_admin(
    admin: PlatformAdminDep,
    session: SessionDep,
    broker_id: Annotated[UUID | None, Query()] = None,
    instrument_id: Annotated[UUID | None, Query()] = None,
    include_inactive: Annotated[bool, Query()] = False,
) -> list[VenueInstrumentResponse]:
    mappings = await VenueInstrumentDirectory(session).list(
        broker_id=broker_id,
        instrument_id=instrument_id,
        include_inactive=include_inactive,
    )
    return [VenueInstrumentResponse.model_validate(mapping) for mapping in mappings]


@admin_router.post(
    "",
    response_model=VenueInstrumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_venue_instrument_admin(
    payload: CreateVenueInstrumentRequest,
    request: Request,
    admin: PlatformAdminDep,
    session: SessionDep,
) -> VenueInstrumentResponse:
    broker = await BrokerDirectory(session).get(payload.broker_id)
    if broker is None or not broker.is_active:
        raise NotFoundError("broker not found or inactive")
    mapping = await VenueInstrumentDirectory(session).create(
        broker_id=payload.broker_id,
        instrument_id=payload.instrument_id,
        venue_symbol=payload.venue_symbol,
        exchange=payload.exchange,
        instrument_token=payload.instrument_token,
        tick_size=payload.tick_size,
        lot_size=payload.lot_size,
        contract_multiplier=payload.contract_multiplier,
        venue_metadata=payload.venue_metadata,
    )
    await AuditService(session).record(
        action="venue_instruments.created",
        resource_type="venue_instrument",
        resource_id=str(mapping.id),
        actor_user_id=admin.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={
            "broker_id": str(mapping.broker_id),
            "instrument_id": str(mapping.instrument_id),
            "venue_symbol": mapping.venue_symbol,
        },
    )
    return VenueInstrumentResponse.model_validate(mapping)


@admin_router.patch("/{mapping_id}", response_model=VenueInstrumentResponse)
async def update_venue_instrument_admin(
    mapping_id: UUID,
    payload: UpdateVenueInstrumentRequest,
    request: Request,
    admin: PlatformAdminDep,
    session: SessionDep,
) -> VenueInstrumentResponse:
    changes = payload.model_dump(exclude_unset=True)
    mapping = await VenueInstrumentDirectory(session).update(mapping_id, **changes)
    await AuditService(session).record(
        action="venue_instruments.updated",
        resource_type="venue_instrument",
        resource_id=str(mapping.id),
        actor_user_id=admin.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={key: str(value) for key, value in changes.items()},
    )
    return VenueInstrumentResponse.model_validate(mapping)
