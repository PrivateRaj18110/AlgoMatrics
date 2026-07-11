"""Contract tests for the Yahoo Finance market-info provider."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from algo_platform.modules.instruments.infrastructure.yahoo_market_info import (
    YahooMarketInfoProvider,
)

pytestmark = pytest.mark.contract


def _chart_payload(price: float, previous: float) -> dict[str, object]:
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "currency": "INR",
                        "symbol": "RELIANCE.NS",
                        "regularMarketPrice": price,
                        "chartPreviousClose": previous,
                        "regularMarketTime": 1752300000,
                    }
                }
            ],
            "error": None,
        }
    }


class TestYahooMarketInfoProvider:
    async def test_parses_snapshot_and_computes_change(self) -> None:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json=_chart_payload(2950.0, 2900.0))

        provider = YahooMarketInfoProvider(transport=httpx.MockTransport(handler))
        snapshot = await provider.snapshot("RELIANCE.NS", symbol="RELIANCE", name="Reliance")
        assert snapshot is not None
        assert snapshot.price == Decimal("2950.0")
        assert snapshot.previous_close == Decimal("2900.0")
        assert snapshot.change == Decimal("50.0")
        assert snapshot.change_pct == Decimal("1.72")
        assert snapshot.currency == "INR"
        assert snapshot.as_of == "1752300000"
        assert "/v8/finance/chart/RELIANCE.NS" in str(calls[0].url)

    async def test_second_call_within_ttl_is_cached(self) -> None:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json=_chart_payload(100.0, 99.0))

        provider = YahooMarketInfoProvider(transport=httpx.MockTransport(handler))
        first = await provider.snapshot("TCS.NS", symbol="TCS", name="TCS")
        second = await provider.snapshot("TCS.NS", symbol="TCS", name="TCS")
        assert first == second
        assert len(calls) == 1

    async def test_failure_returns_none_and_gather_skips(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if "GOOD.NS" in str(request.url):
                return httpx.Response(200, json=_chart_payload(10.0, 10.0))
            return httpx.Response(429, json={"chart": {"result": None}})

        provider = YahooMarketInfoProvider(transport=httpx.MockTransport(handler))
        snapshots = await provider.snapshots(
            [("GOOD.NS", "GOOD", "Good Co"), ("BAD.NS", "BAD", "Bad Co")]
        )
        assert [snapshot.symbol for snapshot in snapshots] == ["GOOD"]

    async def test_malformed_payload_returns_none(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": True})

        provider = YahooMarketInfoProvider(transport=httpx.MockTransport(handler))
        assert await provider.snapshot("^NSEI", symbol="NIFTY 50", name="NIFTY 50") is None
