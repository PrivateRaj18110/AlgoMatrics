"""Market insights: F&O heatmap, pre-market watchlist and market pulse.

Sources, all real:
- NSE pre-open auction for the F&O universe (one fetch each trading morning),
- NSE provisional FII/DII flows (one fetch each evening),
- Yahoo Finance delayed quotes and daily history (cached; shared by all viewers).

Nothing here is simulated. When a source is down the last stored snapshot is
served with its date, and the response says so.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.market_insights.domain.premarket import (
    PreOpenSnapshot,
    build_screens,
    parse_preopen,
)
from algo_platform.modules.market_insights.domain.pulse import (
    InstitutionalFlow,
    Quote,
    breadth,
    parse_fii_dii,
    sector_performance,
    trend_regime,
    volatility_regime,
)
from algo_platform.modules.market_insights.domain.sectors import (
    FALLBACK_FO_UNIVERSE,
    sector_for,
    yahoo_symbol,
)
from algo_platform.modules.market_insights.infrastructure.models import MarketSnapshotModel
from algo_platform.modules.market_insights.infrastructure.nse_client import (
    NseClient,
    NseUnavailable,
)
from algo_platform.modules.market_insights.infrastructure.yahoo_batch import (
    YahooBatchQuotes,
    get_yahoo_batch,
)
from algo_platform.shared.domain.types import utc_now
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway

logger = structlog.get_logger(__name__)

IST = ZoneInfo("Asia/Kolkata")
KIND_PREOPEN = "nse_preopen_fo"
KIND_FII_DII = "nse_fii_dii"

# The pre-open order book freezes at 09:08; a few seconds' grace for NSE to publish.
_PREOPEN_WINDOW = (time(9, 8, 30), time(10, 30))
# By 09:20 an older pre-open date means an exchange holiday, not a late feed.
_PREOPEN_HOLIDAY_AFTER = time(9, 20)
_PREOPEN_RETRY_SECONDS = 300
# NSE posts provisional FII/DII numbers in the evening, sometimes late.
_FII_DII_FROM = time(18, 0)
_FII_DII_GIVE_UP = time(23, 0)
_FII_DII_RETRY_SECONDS = 1800

INDICES: list[tuple[str, str]] = [
    ("^NSEI", "NIFTY 50"),
    ("^NSEBANK", "NIFTY BANK"),
    ("^BSESN", "SENSEX"),
    ("NIFTY_FIN_SERVICE.NS", "FIN NIFTY"),
    ("^CNXIT", "NIFTY IT"),
    ("^NSEMDCP50", "NIFTY MIDCAP 50"),
]
VIX_SYMBOL = "^INDIAVIX"
GLOBAL_CUES: list[tuple[str, str, str]] = [
    ("^GSPC", "S&P 500", "US"),
    ("^IXIC", "Nasdaq", "US"),
    ("^DJI", "Dow Jones", "US"),
    ("^FTSE", "FTSE 100", "Europe"),
    ("^GDAXI", "DAX", "Europe"),
    ("^N225", "Nikkei 225", "Asia"),
    ("^HSI", "Hang Seng", "Asia"),
    ("CL=F", "Crude oil (WTI)", "Commodities"),
    ("GC=F", "Gold", "Commodities"),
    ("INR=X", "USD / INR", "Currency"),
]


def ist_now() -> datetime:
    return utc_now().astimezone(IST)


def market_session(now: datetime | None = None) -> dict[str, Any]:
    """Indian cash-market session by the clock (exchange holidays not modelled)."""
    moment = (now or ist_now()).astimezone(IST)
    clock = moment.time()
    if moment.weekday() >= 5:
        state = "closed"
    elif time(9, 0) <= clock < time(9, 15):
        state = "pre_open"
    elif time(9, 15) <= clock < time(15, 30):
        state = "open"
    else:
        state = "closed"
    return {"state": state, "as_of": moment.isoformat(), "note": "Exchange holidays not shown"}


def _quote_dict(quote: Quote | None, *, symbol: str, name: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "name": name,
        "price": quote.price if quote else None,
        "previous_close": quote.previous_close if quote else None,
        "change_pct": round(quote.change_pct, 2)
        if quote and quote.change_pct is not None
        else None,
        "day_high": quote.day_high if quote else None,
        "day_low": quote.day_low if quote else None,
        "as_of": quote.as_of if quote else None,
    }


class MarketInsightsService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        nse: NseClient | None = None,
        yahoo: YahooBatchQuotes | None = None,
    ) -> None:
        self._session = session
        self._nse = nse or NseClient()
        self._yahoo = yahoo or get_yahoo_batch()

    # -- snapshot storage ----------------------------------------------------------

    async def _latest(
        self, kind: str, trade_date: date | None = None
    ) -> MarketSnapshotModel | None:
        stmt = select(MarketSnapshotModel).where(MarketSnapshotModel.kind == kind)
        if trade_date is not None:
            stmt = stmt.where(MarketSnapshotModel.trade_date == trade_date)
        stmt = stmt.order_by(MarketSnapshotModel.trade_date.desc()).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def _history(self, kind: str, limit: int) -> list[MarketSnapshotModel]:
        stmt = (
            select(MarketSnapshotModel)
            .where(MarketSnapshotModel.kind == kind)
            .order_by(MarketSnapshotModel.trade_date.desc())
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def _store(self, kind: str, trade_date: date, payload: Any) -> None:
        existing = await self._latest(kind, trade_date)
        if existing is not None:
            existing.payload = payload
            existing.fetched_at = utc_now()
        else:
            self._session.add(
                MarketSnapshotModel(
                    kind=kind, trade_date=trade_date, fetched_at=utc_now(), payload=payload
                )
            )
        await self._session.flush()

    # -- NSE refresh ------------------------------------------------------------------

    async def refresh_preopen(self) -> PreOpenSnapshot:
        payload = await self._nse.preopen_fo()
        snapshot = parse_preopen(payload)
        await self._store(KIND_PREOPEN, snapshot.trade_date or ist_now().date(), payload)
        logger.info(
            "market_insights.preopen_stored",
            trade_date=str(snapshot.trade_date),
            stocks=len(snapshot.stocks),
        )
        return snapshot

    async def refresh_fii_dii(self) -> InstitutionalFlow | None:
        payload = await self._nse.fii_dii()
        flow = parse_fii_dii(payload)
        if flow is None:
            raise NseUnavailable("FII/DII feed could not be parsed")
        trade_date = datetime.strptime(flow.trade_date, "%d-%b-%Y").date()
        await self._store(KIND_FII_DII, trade_date, payload)
        return flow

    async def scheduled_tick(self, redis: RedisGateway) -> None:
        """Called every scheduler tick; fetches each daily snapshot at most once."""
        now = ist_now()
        if now.weekday() >= 5:
            return
        start, end = _PREOPEN_WINDOW
        if start <= now.time() <= end:
            await self._maybe_refresh(
                redis,
                kind=KIND_PREOPEN,
                now=now,
                refresh=self._refresh_preopen_date,
                retry_seconds=_PREOPEN_RETRY_SECONDS,
                stale_ok_after=_PREOPEN_HOLIDAY_AFTER,
            )
        if now.time() >= _FII_DII_FROM:
            await self._maybe_refresh(
                redis,
                kind=KIND_FII_DII,
                now=now,
                refresh=self._refresh_fii_dii_date,
                retry_seconds=_FII_DII_RETRY_SECONDS,
                stale_ok_after=_FII_DII_GIVE_UP,
            )

    async def _refresh_preopen_date(self) -> date | None:
        return (await self.refresh_preopen()).trade_date

    async def _refresh_fii_dii_date(self) -> date | None:
        flow = await self.refresh_fii_dii()
        return datetime.strptime(flow.trade_date, "%d-%b-%Y").date() if flow else None

    async def _maybe_refresh(
        self,
        redis: RedisGateway,
        *,
        kind: str,
        now: datetime,
        refresh: Callable[[], Awaitable[date | None]],
        retry_seconds: int,
        stale_ok_after: time,
    ) -> None:
        """Fetch one daily snapshot, at most once per retry window, until today's lands."""
        today = now.date()
        done_key = f"mi:done:{kind}:{today.isoformat()}"
        if await redis.get_str(done_key) is not None:
            return
        if await self._latest(kind, today) is not None:
            await redis.set_str(done_key, "1", ttl_seconds=86_400)
            return
        # One attempt per retry window, shared by every scheduler replica.
        if not await redis.set_if_absent(f"mi:attempt:{kind}", ttl_seconds=retry_seconds):
            return
        try:
            fetched_for = await refresh()
        except NseUnavailable as error:
            logger.warning("market_insights.fetch_failed", kind=kind, error=str(error))
            return
        # Today's data: done. An older date is either a late feed (keep trying)
        # or, past the cut-off, an exchange holiday (stop for the day).
        if fetched_for == today or now.time() >= stale_ok_after:
            await redis.set_str(done_key, "1", ttl_seconds=86_400)

    # -- F&O universe + heatmap -------------------------------------------------------

    async def _universe(self) -> tuple[list[str], dict[str, float], dict[str, Any]]:
        row = await self._latest(KIND_PREOPEN)
        if row is not None:
            snapshot = parse_preopen(row.payload)
            if snapshot.stocks:
                return (
                    [s.symbol for s in snapshot.stocks],
                    {s.symbol: s.market_cap for s in snapshot.stocks},
                    {"source": "nse", "trade_date": row.trade_date.isoformat()},
                )
        return list(FALLBACK_FO_UNIVERSE), {}, {"source": "built_in", "trade_date": None}

    async def _fo_quotes(self) -> tuple[list[dict[str, Any]], list[Quote], dict[str, Any]]:
        symbols, caps, source = await self._universe()
        quotes = await self._yahoo.quotes([yahoo_symbol(s) for s in symbols])
        rows: list[dict[str, Any]] = []
        present: list[Quote] = []
        for symbol in symbols:
            quote = quotes.get(yahoo_symbol(symbol))
            if quote is not None:
                present.append(
                    Quote(**{**asdict(quote), "symbol": symbol})  # key by NSE ticker
                )
            rows.append(
                {
                    **_quote_dict(
                        quote, symbol=symbol, name=(quote.name if quote else None) or symbol
                    ),
                    "sector": sector_for(symbol),
                    "year_high": quote.year_high if quote else None,
                    "year_low": quote.year_low if quote else None,
                    "volume": quote.volume if quote else None,
                    "market_cap": caps.get(symbol) or None,
                }
            )
        return rows, present, source

    async def fo_heatmap(self) -> dict[str, Any]:
        rows, present, source = await self._fo_quotes()
        return {
            "universe": source,
            "session": market_session(),
            "breadth": asdict(breadth(present)),
            "stocks": rows,
            "quoted": len(present),
            "total": len(rows),
        }

    # -- pre-market -------------------------------------------------------------------

    async def premarket(self, trade_date: date | None = None) -> dict[str, Any]:
        row = await self._latest(KIND_PREOPEN, trade_date)
        if row is None:
            return {"available": False, "session": market_session()}
        snapshot = parse_preopen(row.payload)
        stale = row.trade_date != ist_now().date()
        return {
            "available": True,
            "trade_date": row.trade_date.isoformat(),
            "as_of": snapshot.as_of.isoformat() if snapshot.as_of else None,
            "fetched_at": row.fetched_at.isoformat(),
            "stale": stale,
            "session": market_session(),
            "summary": {
                "advances": snapshot.advances,
                "declines": snapshot.declines,
                "unchanged": snapshot.unchanged,
                "total_traded_value": snapshot.total_traded_value,
                "stocks": len(snapshot.stocks),
            },
            "screens": [asdict(screen) for screen in build_screens(snapshot)],
            "stocks": [
                {
                    "symbol": s.symbol,
                    "sector": s.sector,
                    "iep": s.iep,
                    "previous_close": s.previous_close,
                    "change_pct": round(s.change_pct, 2),
                    "imbalance": round(s.imbalance, 3),
                    "buy_quantity": s.buy_quantity,
                    "sell_quantity": s.sell_quantity,
                    "final_quantity": s.final_quantity,
                    "turnover": s.turnover,
                    "market_cap": s.market_cap,
                    "year_high": s.year_high,
                    "year_low": s.year_low,
                }
                for s in snapshot.stocks
            ],
            "disclaimer": (
                "Algorithmic screens computed from the NSE pre-open auction. They rank "
                "situations; they are not investment advice."
            ),
        }

    async def premarket_dates(self, limit: int = 30) -> list[str]:
        return [row.trade_date.isoformat() for row in await self._history(KIND_PREOPEN, limit)]

    # -- pulse --------------------------------------------------------------------------

    async def pulse(self) -> dict[str, Any]:
        index_symbols = [s for s, _ in INDICES] + [VIX_SYMBOL] + [s for s, _, _ in GLOBAL_CUES]
        quotes = await self._yahoo.quotes(index_symbols)
        vix_quote = quotes.get(VIX_SYMBOL)
        nifty_closes = await self._yahoo.daily_closes("^NSEI")
        bank_closes = await self._yahoo.daily_closes("^NSEBANK")
        fo_rows, fo_quotes, universe = await self._fo_quotes()

        movers = sorted(
            (r for r in fo_rows if r["change_pct"] is not None), key=lambda r: r["change_pct"]
        )
        caps = {r["symbol"]: r["market_cap"] or 0.0 for r in fo_rows}
        near_highs = sorted(
            (
                r
                for r in fo_rows
                if r["price"] and r["year_high"] and r["price"] >= 0.98 * r["year_high"]
            ),
            key=lambda r: r["price"] / r["year_high"],
            reverse=True,
        )
        flows = []
        for row in await self._history(KIND_FII_DII, 15):
            flow = parse_fii_dii(row.payload)
            if flow is not None:
                flows.append({**asdict(flow), "trade_date": row.trade_date.isoformat()})

        return {
            "session": market_session(),
            "universe": universe,
            "indices": [_quote_dict(quotes.get(s), symbol=s, name=n) for s, n in INDICES],
            "vix": _quote_dict(vix_quote, symbol=VIX_SYMBOL, name="INDIA VIX"),
            "global": [
                {**_quote_dict(quotes.get(s), symbol=s, name=n), "region": region}
                for s, n, region in GLOBAL_CUES
            ],
            "breadth": asdict(breadth(fo_quotes)),
            "sectors": [
                asdict(m)
                for m in sector_performance(
                    fo_quotes, {r["symbol"]: r["sector"] for r in fo_rows}, caps
                )
            ],
            "gainers": list(reversed(movers[-8:])),
            "losers": movers[:8],
            "near_year_high": near_highs[:10],
            "regime": {
                "nifty": asdict(trend_regime(nifty_closes)),
                "bank_nifty": asdict(trend_regime(bank_closes)),
                "volatility": asdict(volatility_regime(vix_quote.price if vix_quote else None)),
            },
            "institutional_flows": flows,
        }
