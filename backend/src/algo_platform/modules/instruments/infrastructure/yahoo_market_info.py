"""Free Indian market snapshots via Yahoo Finance's public chart API.

Yahoo's ``v8/finance/chart`` endpoint needs no API key and covers NSE/BSE
symbols (``RELIANCE.NS``) and Indian indices (``^NSEI``). Quotes are cached
in-process for a short TTL so dashboard polling never hammers the upstream;
failures degrade to ``None`` per symbol rather than failing the request.
Indian market only — no forex pairs are exposed.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import httpx
import structlog

logger = structlog.get_logger(__name__)

_BASE = "https://query1.finance.yahoo.com"
_TIMEOUT = httpx.Timeout(8.0)
# Yahoo rejects default library user agents.
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AlgoMatrics/1.0)"}
_CACHE_TTL_SECONDS = 60.0

# Headline Indian indices (Yahoo symbol → display name).
INDIAN_INDICES: list[tuple[str, str]] = [
    ("^NSEI", "NIFTY 50"),
    ("^NSEBANK", "NIFTY BANK"),
    ("^BSESN", "SENSEX"),
    ("^CNXIT", "NIFTY IT"),
]


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    symbol: str
    name: str
    yahoo_symbol: str
    price: Decimal | None
    previous_close: Decimal | None
    change: Decimal | None
    change_pct: Decimal | None
    currency: str
    as_of: str | None


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except ArithmeticError:
        return None


class YahooMarketInfoProvider:
    """Fetch + cache spot snapshots for Indian symbols."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport
        self._cache: dict[str, tuple[float, MarketSnapshot | None]] = {}
        self._lock = asyncio.Lock()

    async def snapshot(self, yahoo_symbol: str, *, symbol: str, name: str) -> MarketSnapshot | None:
        now = time.monotonic()
        async with self._lock:
            hit = self._cache.get(yahoo_symbol)
            if hit is not None and now - hit[0] < _CACHE_TTL_SECONDS:
                return hit[1]
        result = await self._fetch(yahoo_symbol, symbol=symbol, name=name)
        async with self._lock:
            self._cache[yahoo_symbol] = (time.monotonic(), result)
        return result

    async def snapshots(self, wanted: list[tuple[str, str, str]]) -> list[MarketSnapshot]:
        """Fetch many symbols concurrently; entries are (yahoo_symbol, symbol, name)."""
        results = await asyncio.gather(
            *(
                self.snapshot(yahoo_symbol, symbol=symbol, name=name)
                for yahoo_symbol, symbol, name in wanted
            )
        )
        return [snapshot for snapshot in results if snapshot is not None]

    async def _fetch(self, yahoo_symbol: str, *, symbol: str, name: str) -> MarketSnapshot | None:
        url = f"{_BASE}/v8/finance/chart/{quote(yahoo_symbol)}"
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT, headers=_HEADERS, transport=self._transport
            ) as client:
                response = await client.get(url, params={"range": "1d", "interval": "1d"})
        except httpx.HTTPError as error:
            logger.warning(
                "market_info.fetch_failed", symbol=yahoo_symbol, error=type(error).__name__
            )
            return None
        if response.status_code != 200:
            logger.warning(
                "market_info.bad_status", symbol=yahoo_symbol, status=response.status_code
            )
            return None
        try:
            body: dict[str, Any] = response.json()
            results = body["chart"]["result"]
            meta: dict[str, Any] = results[0]["meta"]
        except (KeyError, IndexError, TypeError, ValueError):
            logger.warning("market_info.bad_payload", symbol=yahoo_symbol)
            return None

        price = _decimal(meta.get("regularMarketPrice"))
        previous = _decimal(meta.get("chartPreviousClose") or meta.get("previousClose"))
        change: Decimal | None = None
        change_pct: Decimal | None = None
        if price is not None and previous is not None and previous != 0:
            change = price - previous
            change_pct = (change / previous * 100).quantize(Decimal("0.01"))
        market_time = meta.get("regularMarketTime")
        return MarketSnapshot(
            symbol=symbol,
            name=name,
            yahoo_symbol=yahoo_symbol,
            price=price,
            previous_close=previous,
            change=change,
            change_pct=change_pct,
            currency=str(meta.get("currency") or "INR"),
            as_of=str(market_time) if market_time is not None else None,
        )


_provider: YahooMarketInfoProvider | None = None


def get_market_info_provider() -> YahooMarketInfoProvider:
    global _provider
    if _provider is None:
        _provider = YahooMarketInfoProvider()
    return _provider
