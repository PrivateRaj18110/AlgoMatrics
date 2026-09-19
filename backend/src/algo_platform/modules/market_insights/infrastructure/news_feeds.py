"""Indian market headlines from publishers' public RSS feeds.

Only titles, links and publication times are read — never article bodies — and
each feed is fetched at most every few minutes. A feed that is down is skipped;
the rest still count.
"""

from __future__ import annotations

import asyncio

import httpx
import structlog

logger = structlog.get_logger(__name__)

FEEDS: tuple[tuple[str, str], ...] = (
    ("Economic Times", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
    (
        "Economic Times",
        "https://economictimes.indiatimes.com/markets/stocks/news/rssfeeds/2146842.cms",
    ),
    ("Mint", "https://www.livemint.com/rss/markets"),
    ("Mint", "https://www.livemint.com/rss/companies"),
    ("Business Standard", "https://www.business-standard.com/rss/markets-106.rss"),
    ("Business Standard", "https://www.business-standard.com/rss/companies-101.rss"),
    (
        "Google News",
        "https://news.google.com/rss/search?q=NSE+stock+shares+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
    ),
)
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AlgoMatrics/1.0; +https://algomatrics.in)"}
_MAX_BYTES = 2_000_000


class NewsFeeds:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def fetch_all(self) -> list[tuple[str, str]]:
        """(publisher, raw XML) for every feed that answered."""
        async with httpx.AsyncClient(
            headers=_HEADERS,
            timeout=httpx.Timeout(15.0),
            follow_redirects=True,
            transport=self._transport,
        ) as client:
            results = await asyncio.gather(*(self._one(client, name, url) for name, url in FEEDS))
        return [item for item in results if item is not None]

    @staticmethod
    async def _one(client: httpx.AsyncClient, name: str, url: str) -> tuple[str, str] | None:
        try:
            response = await client.get(url)
        except httpx.HTTPError:
            logger.warning("news.feed_failed", feed=name)
            return None
        if response.status_code != 200 or len(response.content) > _MAX_BYTES:
            logger.warning("news.feed_rejected", feed=name, status=response.status_code)
            return None
        return name, response.text
