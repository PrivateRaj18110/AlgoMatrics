"""NSE public data, fetched gently.

NSE serves the JSON behind its own web pages only to browser-like clients that
first load a page (it sets session cookies). This client does exactly that, with
pauses between calls: the pre-open auction and institutional flows once a day,
and the corporate-filings feeds (announcements, event calendar, corporate
actions, large deals, open-interest spurts, the F&O ban list) every few minutes
at most during market hours - never tighter.

NSE may block or reshape these feeds at any time; every failure surfaces as
``NseUnavailable`` and callers keep serving the last stored snapshot.
"""

from __future__ import annotations

import asyncio
from datetime import date
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
_FILINGS_PAGE = f"{_BASE}/companies-listing/corporate-filings-announcements"
_SECBAN_URL = "https://nsearchives.nseindia.com/content/fo/fo_secban.csv"

ANNOUNCEMENTS_PATH = "/api/corporate-announcements?index=equities&from_date={start}&to_date={end}"
EVENT_CALENDAR_PATH = "/api/event-calendar"
CORPORATE_ACTIONS_PATH = "/api/corporates-corporateActions?index=equities"
LARGE_DEALS_PATH = "/api/snapshot-capital-market-largedeal"
OI_SPURTS_PATH = "/api/live-analysis-oi-spurts-underlyings"


def nse_day(value: date) -> str:
    """NSE query dates are dd-mm-yyyy."""
    return value.strftime("%d-%m-%Y")


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

    async def fetch_optional(self, paths: list[str]) -> dict[str, Any]:
        """Several feeds in one session; a feed that fails maps to None instead of raising.

        Raises ``NseUnavailable`` only when NSE cannot be reached at all.
        """
        results: dict[str, Any] = {}
        async with httpx.AsyncClient(
            headers={**_HEADERS, "Referer": _FILINGS_PAGE},
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            transport=self._transport,
        ) as client:
            try:
                await client.get(_FILINGS_PAGE)
            except httpx.HTTPError as error:
                raise NseUnavailable(f"network error: {error}") from error
            for path in paths:
                await asyncio.sleep(_PAUSE_SECONDS)
                try:
                    response = await client.get(f"{_BASE}{path}")
                    results[path] = response.json() if response.status_code == 200 else None
                except (httpx.HTTPError, ValueError):
                    results[path] = None
                if results[path] is None:
                    logger.warning("nse.feed_unavailable", path=path.split("?")[0])
        return results

    async def fo_ban_list(self) -> str | None:
        """Plain-text F&O ban list for the next session (NSE archives host)."""
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": _HEADERS["User-Agent"]},
                timeout=httpx.Timeout(15.0),
                transport=self._transport,
            ) as client:
                response = await client.get(_SECBAN_URL)
        except httpx.HTTPError:
            return None
        return response.text if response.status_code == 200 else None

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
