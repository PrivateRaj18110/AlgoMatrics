"""NSE public data, fetched gently.

NSE serves the JSON behind its own web pages only to browser-like clients that
first load a page (it sets session cookies). This client does exactly that, a
handful of times a day, with pauses between calls. It is used for two daily
snapshots only - the pre-open auction and institutional flows - never polled.

NSE may block or reshape these feeds at any time; every failure surfaces as
``NseUnavailable`` and callers keep serving the last stored snapshot.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

_BASE = "https://www.nseindia.com"
_WARMUP_PAGE = f"{_BASE}/market-data/pre-open-market-cm-and-emerge-market"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": _WARMUP_PAGE,
}
_PAUSE_SECONDS = 1.5


class NseUnavailable(RuntimeError):
    """NSE refused, timed out, or returned something that is not the feed."""


class NseClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def _fetch(self, paths: list[str]) -> list[Any]:
        results: list[Any] = []
        async with httpx.AsyncClient(
            headers=_HEADERS,
            timeout=httpx.Timeout(20.0),
            follow_redirects=True,
            transport=self._transport,
        ) as client:
            try:
                await client.get(_WARMUP_PAGE)
                for path in paths:
                    await asyncio.sleep(_PAUSE_SECONDS)
                    response = await client.get(f"{_BASE}{path}")
                    if response.status_code != 200:
                        raise NseUnavailable(f"{path}: HTTP {response.status_code}")
                    try:
                        results.append(response.json())
                    except ValueError as error:
                        raise NseUnavailable(f"{path}: not JSON") from error
            except httpx.HTTPError as error:
                raise NseUnavailable(f"network error: {error}") from error
        return results

    async def preopen_fo(self) -> dict[str, Any]:
        """Pre-open auction for every F&O stock (also defines the F&O universe)."""
        (payload,) = await self._fetch(["/api/market-data-pre-open?key=FO"])
        if not isinstance(payload, dict) or not payload.get("data"):
            raise NseUnavailable("pre-open feed returned no rows")
        return payload

    async def fii_dii(self) -> list[dict[str, Any]]:
        """Provisional FII/DII cash-market flows for the latest session."""
        (payload,) = await self._fetch(["/api/fiidiiTradeReact"])
        if not isinstance(payload, list) or not payload:
            raise NseUnavailable("FII/DII feed returned no rows")
        return payload
