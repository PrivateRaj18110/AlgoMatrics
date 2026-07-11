"""Indian market information (indices + NSE quotes) from a free provider."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from algo_platform.api.dependencies.core import SessionDep
from algo_platform.api.dependencies.tenant import TenantContext, require_permission
from algo_platform.modules.instruments.infrastructure.models import InstrumentModel
from algo_platform.modules.instruments.infrastructure.yahoo_market_info import (
    INDIAN_INDICES,
    get_market_info_provider,
)
from algo_platform.modules.organizations.domain.roles import Permission

router = APIRouter(prefix="/market-info", tags=["market-info"])

AnalyticsTenant = Annotated[TenantContext, Depends(require_permission(Permission.ANALYTICS_VIEW))]

_MAX_SYMBOLS = 25


class MarketInfoResponse(BaseModel):
    symbol: str
    name: str
    yahoo_symbol: str
    price: Decimal | None
    previous_close: Decimal | None
    change: Decimal | None
    change_pct: Decimal | None
    currency: str
    as_of: str | None


@router.get("/indices", response_model=list[MarketInfoResponse])
async def indices(tenant: AnalyticsTenant) -> list[MarketInfoResponse]:
    """Headline Indian indices (NIFTY 50, NIFTY BANK, SENSEX, NIFTY IT)."""
    provider = get_market_info_provider()
    snapshots = await provider.snapshots(
        [(yahoo_symbol, name, name) for yahoo_symbol, name in INDIAN_INDICES]
    )
    return [
        MarketInfoResponse.model_validate(snapshot, from_attributes=True) for snapshot in snapshots
    ]


@router.get("/quotes", response_model=list[MarketInfoResponse])
async def quotes(
    tenant: AnalyticsTenant,
    session: SessionDep,
    symbols: Annotated[
        str | None, Query(description="comma-separated NSE symbols, e.g. RELIANCE,TCS")
    ] = None,
) -> list[MarketInfoResponse]:
    """Delayed NSE spot quotes. Defaults to the platform's active NSE equities."""
    if symbols:
        wanted_symbols = [part.strip().upper() for part in symbols.split(",") if part.strip()][
            :_MAX_SYMBOLS
        ]
        names = {symbol: symbol for symbol in wanted_symbols}
    else:
        stmt = (
            select(InstrumentModel)
            .where(
                InstrumentModel.is_active,
                InstrumentModel.exchange == "NSE",
                InstrumentModel.asset_class == "equity",
            )
            .order_by(InstrumentModel.symbol)
            .limit(_MAX_SYMBOLS)
        )
        rows = (await session.execute(stmt)).scalars().all()
        wanted_symbols = [row.symbol for row in rows]
        names = {row.symbol: row.name for row in rows}
    provider = get_market_info_provider()
    snapshots = await provider.snapshots(
        [(f"{symbol}.NS", symbol, names[symbol]) for symbol in wanted_symbols]
    )
    return [
        MarketInfoResponse.model_validate(snapshot, from_attributes=True) for snapshot in snapshots
    ]
