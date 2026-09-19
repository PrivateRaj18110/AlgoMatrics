"""Market insights: NSE pre-open parsing, screens, pulse maths, daily fetch policy.

The pre-open fixture is a trimmed copy of a real NSE response (18-Sep-2026),
so the parser is tested against what NSE actually sends.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from algo_platform.modules.market_insights.application import service as service_module
from algo_platform.modules.market_insights.application.service import (
    IST,
    KIND_FII_DII,
    KIND_PREOPEN,
    MarketInsightsService,
    market_session,
)
from algo_platform.modules.market_insights.domain.premarket import (
    MIN_GAP_PCT,
    MIN_IMBALANCE,
    build_screens,
    parse_preopen,
)
from algo_platform.modules.market_insights.domain.pulse import (
    Quote,
    breadth,
    parse_fii_dii,
    rsi,
    sector_performance,
    sma,
    trend_regime,
    volatility_regime,
)
from algo_platform.modules.market_insights.domain.sectors import sector_for, yahoo_symbol
from algo_platform.modules.market_insights.infrastructure.nse_client import NseUnavailable

FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "nse_market_sample.json").read_text("utf-8")
)


# -- pre-open parsing -------------------------------------------------------------------


def test_parse_real_preopen_payload() -> None:
    snapshot = parse_preopen(FIXTURE["preopen_fo"])
    assert snapshot.trade_date == date(2026, 9, 18)
    assert snapshot.as_of == datetime(2026, 9, 18, 9, 8, 37)
    assert (snapshot.advances, snapshot.declines) == (142, 41)
    assert len(snapshot.stocks) == 40
    stock = snapshot.stocks[0]
    assert stock.iep > 0 and stock.previous_close > 0
    assert -1.0 <= stock.imbalance <= 1.0
    assert stock.sector != ""


def test_parser_skips_rows_without_symbol_and_tolerates_junk() -> None:
    snapshot = parse_preopen(
        {"timestamp": "bad", "data": [{"metadata": {}}, {"metadata": {"symbol": "X"}}]}
    )
    assert [s.symbol for s in snapshot.stocks] == ["X"]
    assert snapshot.trade_date is None
    assert snapshot.stocks[0].imbalance == 0.0


def test_screens_obey_their_own_rules() -> None:
    screens = {s.key: s for s in build_screens(parse_preopen(FIXTURE["preopen_fo"]))}
    assert set(screens) == {"momentum_up", "momentum_down", "reversal", "breakout"}
    for pick in screens["momentum_up"].picks:
        assert pick.change_pct >= MIN_GAP_PCT and pick.imbalance >= MIN_IMBALANCE
        assert pick.bias == "long" and pick.reasons
    for pick in screens["momentum_down"].picks:
        assert pick.change_pct <= -MIN_GAP_PCT and pick.imbalance <= -MIN_IMBALANCE
    for pick in screens["reversal"].picks:
        assert (pick.change_pct > 0) != (pick.imbalance > 0)
    for screen in screens.values():
        scores = [p.score for p in screen.picks]
        assert scores == sorted(scores, reverse=True)
        assert len(screen.picks) <= 6


def test_real_morning_produces_at_least_one_pick() -> None:
    screens = build_screens(parse_preopen(FIXTURE["preopen_fo"]))
    assert sum(len(s.picks) for s in screens) > 0


def test_empty_book_produces_no_screens() -> None:
    assert build_screens(parse_preopen({"data": []})) == []


# -- sectors -----------------------------------------------------------------------------


def test_every_fixture_stock_has_a_real_sector() -> None:
    for row in FIXTURE["preopen_fo"]["data"]:
        assert sector_for(row["metadata"]["symbol"]) != "Other", row["metadata"]["symbol"]


def test_unknown_symbol_is_other_not_dropped() -> None:
    assert sector_for("NEWLISTING") == "Other"
    assert yahoo_symbol("m&m") == "M&M.NS"


# -- pulse maths ---------------------------------------------------------------------------


def _quote(symbol: str, price: float, prev: float, **extra: float) -> Quote:
    return Quote(
        symbol=symbol,
        name=symbol,
        price=price,
        previous_close=prev,
        day_high=extra.get("day_high"),
        day_low=extra.get("day_low"),
        year_high=extra.get("year_high"),
        year_low=extra.get("year_low"),
        volume=None,
        as_of=None,
    )


def test_breadth_counts_and_52_week_proximity() -> None:
    quotes = [
        _quote("A", 102, 100, year_high=103),
        _quote("B", 98, 100, year_low=97),
        _quote("C", 100.01, 100),
        _quote("D", 110, 100),
    ]
    result = breadth(quotes)
    assert (result.advances, result.declines, result.unchanged) == (2, 1, 1)
    assert result.ratio == 2.0 and result.pct_advancing == 50.0
    assert (result.near_year_high, result.near_year_low) == (1, 1)


def test_sector_change_is_market_cap_weighted() -> None:
    quotes = [_quote("BIG", 101, 100), _quote("SMALL", 90, 100)]
    (move,) = sector_performance(quotes, {"BIG": "Banks", "SMALL": "Banks"}, {"BIG": 9, "SMALL": 1})
    assert move.change_pct == pytest.approx(-0.1)  # (1*9 - 10*1) / 10
    assert (move.leader, move.laggard, move.advancing) == ("BIG", "SMALL", 1)


def test_sma_and_rsi_basics() -> None:
    assert sma([1, 2, 3, 4], 2) == 3.5 and sma([1], 2) is None
    assert rsi(list(range(1, 40))) == 100.0
    assert rsi(list(range(40, 1, -1))) == 0.0
    assert rsi([1, 2]) is None


@pytest.mark.parametrize(
    ("closes", "label"),
    [
        ([100.0 + i for i in range(250)], "Uptrend"),
        ([400.0 - i for i in range(250)], "Downtrend"),
        ([100.0] * 10, "Unknown"),
    ],
)
def test_trend_regime(closes: list[float], label: str) -> None:
    assert trend_regime(closes).label == label


@pytest.mark.parametrize(
    ("vix", "label"),
    [(11.4, "Calm"), (15.0, "Normal"), (20.0, "Elevated"), (31.0, "Stressed"), (None, "Unknown")],
)
def test_volatility_bands(vix: float | None, label: str) -> None:
    assert volatility_regime(vix).label == label


def test_parse_real_fii_dii() -> None:
    flow = parse_fii_dii(FIXTURE["fii_dii"])
    assert flow is not None and flow.trade_date == "18-Sep-2026"
    assert flow.fii_net == pytest.approx(599.54) and flow.dii_net == pytest.approx(1019.69)
    assert parse_fii_dii("nope") is None and parse_fii_dii([]) is None


def test_market_session_by_clock() -> None:
    assert market_session(datetime(2026, 9, 18, 9, 5, tzinfo=IST))["state"] == "pre_open"
    assert market_session(datetime(2026, 9, 18, 11, 0, tzinfo=IST))["state"] == "open"
    assert market_session(datetime(2026, 9, 18, 16, 0, tzinfo=IST))["state"] == "closed"
    assert market_session(datetime(2026, 9, 19, 11, 0, tzinfo=IST))["state"] == "closed"  # Sat


# -- daily fetch policy ----------------------------------------------------------------------


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get_str(self, key: str) -> str | None:
        return self.values.get(key)

    async def set_str(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value

    async def set_if_absent(self, key: str, *, ttl_seconds: int) -> bool:
        if key in self.values:
            return False
        self.values[key] = "1"
        return True


class Harness(MarketInsightsService):
    """Service with storage and NSE replaced by in-memory fakes."""

    def __init__(self, fetched_for: date | None, *, fail: bool = False) -> None:
        self.stored: dict[str, date] = {}
        self.calls = 0
        self._fetched_for = fetched_for
        self._fail = fail

    async def _latest(self, kind: str, trade_date: date | None = None) -> Any:
        return object() if self.stored.get(kind) == trade_date else None

    async def _refresh_preopen_date(self) -> date | None:
        return await self._fake(KIND_PREOPEN)

    async def _refresh_fii_dii_date(self) -> date | None:
        return await self._fake(KIND_FII_DII)

    async def _fake(self, kind: str) -> date | None:
        self.calls += 1
        if self._fail:
            raise NseUnavailable("blocked")
        if self._fetched_for is not None:
            self.stored[kind] = self._fetched_for
        return self._fetched_for


def _at(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    monkeypatch.setattr(service_module, "ist_now", lambda: moment)


async def test_preopen_fetched_once_on_a_trading_morning(monkeypatch: pytest.MonkeyPatch) -> None:
    today = date(2026, 9, 18)
    _at(monkeypatch, datetime(2026, 9, 18, 9, 9, tzinfo=IST))
    service, redis = Harness(today), FakeRedis()
    await service.scheduled_tick(redis)  # type: ignore[arg-type]
    await service.scheduled_tick(redis)  # type: ignore[arg-type]
    assert service.calls == 1


async def test_nothing_fetched_outside_windows_or_on_weekends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for moment in (
        datetime(2026, 9, 18, 8, 0, tzinfo=IST),
        datetime(2026, 9, 19, 9, 9, tzinfo=IST),
    ):
        _at(monkeypatch, moment)
        service = Harness(moment.date())
        await service.scheduled_tick(FakeRedis())  # type: ignore[arg-type]
        assert service.calls == 0


async def test_late_feed_keeps_trying_until_the_holiday_cutoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    yesterday = date(2026, 9, 17)
    redis = FakeRedis()
    _at(monkeypatch, datetime(2026, 9, 18, 9, 9, tzinfo=IST))
    service = Harness(yesterday)
    await service.scheduled_tick(redis)  # type: ignore[arg-type]
    assert "mi:done:nse_preopen_fo:2026-09-18" not in redis.values  # try again later

    redis.values.pop("mi:attempt:nse_preopen_fo")  # retry window elapsed
    _at(monkeypatch, datetime(2026, 9, 18, 9, 25, tzinfo=IST))
    await service.scheduled_tick(redis)  # type: ignore[arg-type]
    assert redis.values["mi:done:nse_preopen_fo:2026-09-18"] == "1"  # holiday: stop


async def test_failures_back_off_instead_of_hammering(monkeypatch: pytest.MonkeyPatch) -> None:
    _at(monkeypatch, datetime(2026, 9, 18, 9, 10, tzinfo=IST))
    service, redis = Harness(None, fail=True), FakeRedis()
    for _ in range(5):
        await service.scheduled_tick(redis)  # type: ignore[arg-type]
    assert service.calls == 1


async def test_fii_dii_waits_for_the_evening(monkeypatch: pytest.MonkeyPatch) -> None:
    _at(monkeypatch, datetime(2026, 9, 18, 18, 30, tzinfo=IST))
    service = Harness(date(2026, 9, 18))
    await service.scheduled_tick(FakeRedis())  # type: ignore[arg-type]
    assert service.stored == {KIND_FII_DII: date(2026, 9, 18)}
