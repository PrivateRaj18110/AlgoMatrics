"""Batched delayed quotes and daily history from Yahoo Finance.

``v7/finance/spark`` returns up to 20 symbols per request with price, previous
close, day range, 52-week range and volume, so the whole F&O universe costs ~11
requests. Results are cached per symbol for a minute, and history for half an
hour, so any number of viewers share the same upstream calls.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import structlog

from algo_platform.modules.market_insights.domain.pulse import Quote

logger = structlog.get_logger(__name__)

_BASE = "https://query1.finance.yahoo.com"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AlgoMatrics/1.0)"}
_BATCH = 20
_QUOTE_TTL = 60.0
_HISTORY_TTL = 1800.0
_IST = ZoneInfo("Asia/Kolkata")


def _float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


class YahooBatchQuotes:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport
        self._quotes: dict[str, tuple[float, Quote | None]] = {}
        self._history: dict[str, tuple[float, list[float]]] = {}
        self._lock = asyncio.Lock()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=_BASE, headers=_HEADERS, timeout=httpx.Timeout(10.0), transport=self._transport
        )

    async def quotes(self, symbols: list[str]) -> dict[str, Quote | None]:
        """Yahoo symbol -> quote (None when Yahoo has nothing for it)."""
        now = time.monotonic()
        async with self._lock:
            stale = [
                s
                for s in dict.fromkeys(symbols)
                if s not in self._quotes or now - self._quotes[s][0] >= _QUOTE_TTL
            ]
            if stale:
                async with self._client() as client:
                    chunks = [stale[i : i + _BATCH] for i in range(0, len(stale), _BATCH)]
                    fetched = await asyncio.gather(
                        *(self._spark(client, chunk) for chunk in chunks)
                    )
                stamp = time.monotonic()
                for chunk, result in zip(chunks, fetched, strict=True):
                    for symbol in chunk:
                        self._quotes[symbol] = (stamp, result.get(symbol))
            return {s: self._quotes.get(s, (0.0, None))[1] for s in symbols}

    async def _spark(self, client: httpx.AsyncClient, symbols: list[str]) -> dict[str, Quote]:
        try:
            response = await client.get(
                "/v7/finance/spark",
                params={"symbols": ",".join(symbols), "range": "1d", "interval": "1d"},
            )
            response.raise_for_status()
            results = (response.json().get("spark") or {}).get("result") or []
        except (httpx.HTTPError, ValueError):
            logger.warning("yahoo.spark_failed", symbols=len(symbols))
            return {}
        quotes: dict[str, Quote] = {}
        for item in results:
            responses = item.get("response") or []
            meta = (responses[0] or {}).get("meta") if responses else None
            if not meta:
                continue
            quotes[item.get("symbol")] = Quote(
                symbol=item.get("symbol"),
                name=meta.get("shortName") or meta.get("longName"),
                price=_float(meta.get("regularMarketPrice")),
                previous_close=_float(meta.get("chartPreviousClose") or meta.get("previousClose")),
                day_high=_float(meta.get("regularMarketDayHigh")),
                day_low=_float(meta.get("regularMarketDayLow")),
                year_high=_float(meta.get("fiftyTwoWeekHigh")),
                year_low=_float(meta.get("fiftyTwoWeekLow")),
                volume=_float(meta.get("regularMarketVolume")),
                as_of=meta.get("regularMarketTime"),
            )
        return quotes

    async def daily_closes(self, symbol: str, *, range_: str = "1y") -> list[float]:
        now = time.monotonic()
        hit = self._history.get(symbol)
        if hit and now - hit[0] < _HISTORY_TTL:
            return hit[1]
        try:
            async with self._client() as client:
                response = await client.get(
                    f"/v8/finance/chart/{symbol}", params={"range": range_, "interval": "1d"}
                )
                response.raise_for_status()
                result = response.json()["chart"]["result"][0]
            closes = [
                float(c) for c in result["indicators"]["quote"][0].get("close", []) if c is not None
            ]
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            logger.warning("yahoo.history_failed", symbol=symbol)
            return hit[1] if hit else []
        self._history[symbol] = (time.monotonic(), closes)
        return closes

    async def closes_batch(
        self, symbols: list[str], *, range_: str = "3mo"
    ) -> dict[str, list[tuple[date, float]]]:
        """Daily closes for many symbols, 20 per request (spark). Not cached."""
        out: dict[str, list[tuple[date, float]]] = {}
        chunks = [symbols[i : i + _BATCH] for i in range(0, len(symbols), _BATCH)]
        async with self._client() as client:
            for chunk in chunks:
                try:
                    response = await client.get(
                        "/v7/finance/spark",
                        params={"symbols": ",".join(chunk), "range": range_, "interval": "1d"},
                    )
                    response.raise_for_status()
                    results = (response.json().get("spark") or {}).get("result") or []
                except (httpx.HTTPError, ValueError):
                    logger.warning("yahoo.spark_history_failed", symbols=len(chunk))
                    continue
                for item in results:
                    responses = item.get("response") or []
                    body = responses[0] if responses else None
                    if not body:
                        continue
                    stamps = body.get("timestamp") or []
                    closes = ((body.get("indicators") or {}).get("quote") or [{}])[0].get(
                        "close"
                    ) or []
                    out[item.get("symbol")] = [
                        (_ist_date(ts), float(close))
                        for ts, close in zip(stamps, closes, strict=False)
                        if ts is not None and close is not None
                    ]
                await asyncio.sleep(0.3)
        return out

    async def daily_bars(self, symbol: str, *, range_: str = "6mo") -> list[DailyBar]:
        """Daily open/high/low/close for one symbol (chart API). Not cached."""
        try:
            async with self._client() as client:
                response = await client.get(
                    f"/v8/finance/chart/{symbol}", params={"range": range_, "interval": "1d"}
                )
                response.raise_for_status()
                result = response.json()["chart"]["result"][0]
            quote = result["indicators"]["quote"][0]
            stamps = result.get("timestamp") or []
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            logger.warning("yahoo.bars_failed", symbol=symbol)
            return []
        bars: list[DailyBar] = []
        for i, ts in enumerate(stamps):
            values = [
                quote.get(key, [None] * len(stamps))[i] for key in ("open", "high", "low", "close")
            ]
            if ts is None or any(v is None for v in values):
                continue
            bars.append(DailyBar(_ist_date(ts), *(float(v) for v in values)))
        return bars


@dataclass(frozen=True, slots=True)
class DailyBar:
    day: date
    open: float
    high: float
    low: float
    close: float


def _ist_date(timestamp: int) -> date:
    return datetime.fromtimestamp(int(timestamp), tz=_IST).date()


_shared = YahooBatchQuotes()


def get_yahoo_batch() -> YahooBatchQuotes:
    return _shared
