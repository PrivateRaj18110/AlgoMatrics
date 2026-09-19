"""AI-CIO movers radar: filing classification, the move model, grading and the service.

No network, database or Redis: small fakes stand in for NSE, Yahoo, the news
feeds, the snapshot store and Redis.
"""

from __future__ import annotations

import json
import random
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from typing import Any

import pytest

from algo_platform.modules.market_insights.application import movers as movers_module
from algo_platform.modules.market_insights.application.movers import (
    KIND_CATALYSTS,
    KIND_FORECAST,
    KIND_MODEL,
    KIND_OUTCOME,
    KIND_PREOPEN,
    KIND_SAMPLES,
    MoversService,
)
from algo_platform.modules.market_insights.domain.catalysts import (
    IST,
    Catalyst,
    classify_filing,
    impact_total,
    name_index,
    overnight_window,
    parse_announcements,
    parse_corporate_actions,
    parse_event_calendar,
    parse_large_deals,
    parse_oi_spurts,
    parse_rss,
    parse_secban,
    tag_headlines,
)
from algo_platform.modules.market_insights.domain.move_model import (
    FEATURES,
    PRIOR_WEIGHTS,
    StockInputs,
    calibration,
    direction_call,
    feature_vector,
    fit_logistic,
    grade_day,
    history_stats,
    is_major,
    major_threshold,
    prior_model,
    stage_vector,
    summarise,
)
from algo_platform.modules.market_insights.domain.pulse import Quote
from algo_platform.modules.market_insights.infrastructure.ai_reader import parse_assessments
from algo_platform.modules.market_insights.infrastructure.yahoo_batch import DailyBar

# --------------------------------------------------------------------------------------
# Filing classification
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("subject", "text", "category"),
    [
        ("Outcome of Board Meeting", "Approved unaudited financial results for Q1", "results"),
        (
            "Board Meeting Intimation",
            "Meeting to be held to consider financial results",
            "results_scheduled",
        ),
        (
            "Action(s) taken or orders passed",
            "GST demand order of Rs 12 crore received",
            "regulatory",
        ),
        (
            "Bagging/Receiving of orders/contracts",
            "Received an order worth Rs 450 crore",
            "order_win",
        ),
        (
            "Disclosure under SEBI Takeover Regulations",
            "Acquisition of shares by promoter",
            "insider",
        ),
        ("Updates", "Clarification on news item appearing in media", "clarification"),
        ("Credit Rating- Revision", "ICRA has upgraded the long term rating", "rating_up"),
        ("Credit Rating", "CRISIL has downgraded the rating", "rating_down"),
        ("Resignation of Director/KMP/SMP", "Resignation of Chief Financial Officer", "top_exit"),
        ("Trading Window", "Closure of trading window", "routine"),
        ("Acquisition", "Acquisition of 51% stake in ABC Ltd", "m_and_a"),
        ("Buyback", "Board approves buyback of equity shares", "buyback"),
    ],
)
def test_filings_are_classified_by_what_they_mean(subject: str, text: str, category: str) -> None:
    assert classify_filing(subject, text)[0] == category


def test_routine_paperwork_weighs_almost_nothing_and_results_weigh_most() -> None:
    routine = classify_filing("Copy of Newspaper Publication", "Newspaper advertisement")[2]
    results = classify_filing("Financial Result Updates", "Audited standalone results")[2]
    assert routine < 0.05 < 0.8 < results


def _announcement(symbol: str, subject: str, text: str, at: str, seq: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "desc": subject,
        "attchmntText": text,
        "sort_date": at,
        "an_dt": at,
        "seq_id": seq,
        "sm_name": f"{symbol} Limited",
        "attchmntFile": f"https://nsearchives.nseindia.com/corporate/{seq}.pdf",
    }


def test_announcements_keep_only_the_universe_with_times_and_links() -> None:
    rows = [
        _announcement(
            "TCS", "Press Release", "TCS wins order worth Rs 900 crore", "2026-09-18 19:02:10", "1"
        ),
        _announcement("TINYCO", "Press Release", "Not in F&O", "2026-09-18 19:05:00", "2"),
    ]
    [item] = parse_announcements(rows, {"TCS"})
    assert item.symbol == "TCS"
    assert item.category == "order_win"
    assert item.at == datetime(2026, 9, 18, 19, 2, 10, tzinfo=IST)
    assert item.url and item.url.endswith("1.pdf")
    assert Catalyst.from_dict(json.loads(json.dumps(item.as_dict()))) == item


def test_event_calendar_flags_results_today_only() -> None:
    day = date(2026, 9, 21)
    rows = [
        {
            "symbol": "INFY",
            "date": "21-Sep-2026",
            "purpose": "Financial Results",
            "bm_desc": "Q2 results",
        },
        {
            "symbol": "TCS",
            "date": "22-Sep-2026",
            "purpose": "Financial Results",
            "bm_desc": "Q2 results",
        },
        {
            "symbol": "WIPRO",
            "date": "21-Sep-2026",
            "purpose": "Other business matters",
            "bm_desc": "",
        },
    ]
    items = parse_event_calendar(rows, {"INFY", "TCS", "WIPRO"}, day)
    assert [(c.symbol, c.category) for c in items] == [("INFY", "results_today")]


def test_bonus_ex_date_is_marked_as_a_mechanical_reprice() -> None:
    rows = [
        {"symbol": "ABC", "exDate": "21-Sep-2026", "subject": "Bonus 1:1", "comp": "ABC Ltd"},
        {"symbol": "XYZ", "exDate": "21-Sep-2026", "subject": "Dividend - Rs 2 Per Share"},
    ]
    items = {c.symbol: c for c in parse_corporate_actions(rows, {"ABC", "XYZ"}, date(2026, 9, 21))}
    assert items["ABC"].category == "ex_adjustment"
    assert items["XYZ"].category == "ex_dividend"


def test_ban_list_deals_and_oi_spurts() -> None:
    ban_day, symbols = parse_secban(
        "Securities in Ban For Trade Date 21-SEP-2026:\n1,SAIL\n2,IDEA\n"
    )
    assert ban_day == date(2026, 9, 21)
    assert symbols == {"SAIL", "IDEA"}
    deals = parse_large_deals(
        {
            "BLOCK_DEALS_DATA": [
                {
                    "symbol": "SAIL",
                    "buySell": "BUY",
                    "clientName": "Fund",
                    "qty": "100",
                    "watp": "1",
                    "date": "18-Sep-2026",
                }
            ]
        },
        {"SAIL"},
    )
    assert deals[0].direction == 1 and deals[0].source == "block_deal"
    oi = parse_oi_spurts({"data": [{"symbol": "TCS", "latestOI": 130, "prevOI": 100}]}, {"TCS"})
    assert oi == {"TCS": 30.0}


def test_combined_impact_never_exceeds_one() -> None:
    assert impact_total([0.5, 0.5]) == 0.75
    assert impact_total([]) == 0.0
    assert impact_total([1.0, 0.9]) == 1.0


def test_monday_overnight_window_starts_at_friday_close() -> None:
    start, end = overnight_window(date(2026, 9, 21))  # Monday
    assert start == datetime(2026, 9, 18, 15, 30, tzinfo=IST)
    assert end == datetime(2026, 9, 21, 9, 8, tzinfo=IST)


# --------------------------------------------------------------------------------------
# Headlines
# --------------------------------------------------------------------------------------

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>HDFC Bank shares surge after strong Q2 results</title><link>https://example.com/a</link>
<pubDate>Fri, 18 Sep 2026 17:00:00 +0530</pubDate></item>
<item><title>Infosys slumps as client cuts spending</title><link>https://example.com/b</link>
<pubDate>Fri, 18 Sep 2026 18:00:00 +0530</pubDate></item>
<item><title>Monsoon covers most of India</title><link>https://example.com/c</link>
<pubDate>Fri, 18 Sep 2026 18:30:00 +0530</pubDate></item>
</channel></rss>"""


def test_headlines_are_tagged_with_the_stocks_they_name() -> None:
    items = parse_rss(RSS, "Test Wire")
    index = name_index(
        {"HDFCBANK": "HDFC Bank Limited", "INFY": "Infosys Limited", "ITC": "ITC Limited"}
    )
    tagged = {h.title: h for h in tag_headlines(items, index)}
    assert tagged["HDFC Bank shares surge after strong Q2 results"].symbols == ["HDFCBANK"]
    assert tagged["HDFC Bank shares surge after strong Q2 results"].sentiment == 1
    assert tagged["Infosys slumps as client cuts spending"].symbols == ["INFY"]
    assert tagged["Infosys slumps as client cuts spending"].sentiment == -1
    # "India" is not a company: no false match on a generic word.
    assert tagged["Monsoon covers most of India"].symbols == []


def test_rss_with_a_dtd_is_refused() -> None:
    evil = (
        '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]>'
        "<rss><channel><item><title>&a;</title></item></channel></rss>"
    )
    assert parse_rss(evil, "x") == []
    assert parse_rss("not xml at all", "x") == []


# --------------------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------------------


def _closes(daily_moves: Sequence[float], start: float = 100.0) -> list[float]:
    closes = [start]
    for move in daily_moves:
        closes.append(closes[-1] * (1 + move / 100))
    return closes


def test_major_move_bar_scales_with_the_stocks_own_volatility() -> None:
    quiet = history_stats(_closes([0.5, -0.5] * 12))
    wild = history_stats(_closes([3.0, -3.0] * 12))
    assert quiet is not None and wild is not None
    assert major_threshold(quiet.typical_move) == 3.0
    assert major_threshold(wild.typical_move) == pytest.approx(6.0, abs=0.2)
    assert is_major(3.5, quiet.typical_move)
    assert not is_major(3.5, wild.typical_move)


def test_short_history_gives_no_stats_rather_than_a_guess() -> None:
    assert history_stats(_closes([1.0] * 5)) is None


def test_overnight_stage_cannot_see_the_auction() -> None:
    stats = history_stats(_closes([1.0, -1.0] * 12))
    assert stats is not None
    features = feature_vector(StockInputs("X", stats, gap_pct=4.0, imbalance=0.6))
    overnight = dict(zip(FEATURES, stage_vector(features, "overnight"), strict=True))
    opening = dict(zip(FEATURES, stage_vector(features, "opening"), strict=True))
    assert overnight["gap_z"] == overnight["gap_abs"] == overnight["imbalance"] == 0.0
    assert opening["gap_z"] > 3 and opening["imbalance"] == 0.6


def test_bigger_gap_and_fresh_results_raise_the_probability() -> None:
    stats = history_stats(_closes([1.0, -1.0] * 12))
    assert stats is not None
    model = prior_model()["opening"]
    calm = model.probability(
        stage_vector(feature_vector(StockInputs("A", stats, gap_pct=0.1)), "opening")
    )
    gap = model.probability(
        stage_vector(feature_vector(StockInputs("B", stats, gap_pct=4.0)), "opening")
    )
    both = model.probability(
        stage_vector(
            feature_vector(StockInputs("C", stats, gap_pct=4.0, results=True, catalyst_impact=0.9)),
            "opening",
        )
    )
    assert calm < gap < both
    assert calm < 0.1


def test_fit_learns_a_real_signal_and_keeps_priors_where_history_is_blind() -> None:
    rng = random.Random(7)
    rows: list[list[float]] = []
    labels: list[int] = []
    for _ in range(3000):
        catalyst = 1.0 if rng.random() < 0.15 else 0.0
        vector = [0.0] * len(FEATURES)
        vector[FEATURES.index("catalyst")] = catalyst
        vector[FEATURES.index("typical")] = rng.uniform(0.5, 2.5)
        rows.append(vector)
        labels.append(int(rng.random() < (0.6 if catalyst else 0.03)))
    fitted = fit_logistic(rows, labels, prior=prior_model()["overnight"], ridge=1.0)
    assert fitted.weights["catalyst"] > PRIOR_WEIGHTS["catalyst"]
    # News never varies in this data: its weight stays exactly at the prior.
    assert fitted.weights["news"] == pytest.approx(PRIOR_WEIGHTS["news"])


def test_direction_follows_the_gap_then_the_filings() -> None:
    assert (
        direction_call(gap_pct=2.5, imbalance=0.4, catalyst_direction=0, news_sentiment=0).direction
        == "up"
    )
    assert (
        direction_call(
            gap_pct=2.5, imbalance=0.4, catalyst_direction=0, news_sentiment=0
        ).confidence
        == "high"
    )
    assert (
        direction_call(
            gap_pct=-2.0, imbalance=0.4, catalyst_direction=0, news_sentiment=0
        ).confidence
        == "medium"
    )
    assert (
        direction_call(
            gap_pct=None, imbalance=None, catalyst_direction=-0.55, news_sentiment=0
        ).direction
        == "down"
    )
    assert (
        direction_call(
            gap_pct=0.2, imbalance=None, catalyst_direction=0.0, news_sentiment=1
        ).direction
        == "either"
    )


def test_grading_counts_hits_against_the_base_rate() -> None:
    predictions = [(f"S{i}", 1 - i / 100, "up") for i in range(20)]
    outcomes = {f"S{i}": (i in (0, 1, 15), 5.0 if i != 1 else -5.0) for i in range(20)}
    grade = grade_day(predictions, outcomes, top_k=10)
    assert grade.hits == 2 and grade.majors == 3 and grade.universe == 20
    assert grade.precision == 0.2
    assert grade.base_rate == 0.15
    assert grade.lift == pytest.approx(0.2 / 0.15)
    assert grade.direction_calls == 2 and grade.direction_right == 1
    assert grade.missed_symbols == ["S15"]
    pooled = summarise([grade.as_dict(), grade.as_dict()])
    assert pooled["hits"] == 4 and pooled["precision"] == 0.2


def test_calibration_bands_compare_predicted_with_actual() -> None:
    bands = calibration([(0.02, False), (0.03, True), (0.4, True), (0.45, False)])
    assert bands[0]["count"] == 2 and bands[0]["actual"] == 0.5
    assert bands[-1]["predicted"] == pytest.approx(0.425)


def test_ai_reader_replies_are_parsed_defensively() -> None:
    reply = (
        'Sure: [{"id": "nse:1", "impact": 1.7, "direction": -3, "note": "Big penalty"},'
        ' {"id": "other"}]'
    )
    parsed = parse_assessments(reply, {"nse:1"})
    assert parsed["nse:1"].impact == 1.0 and parsed["nse:1"].direction == -1
    assert parse_assessments("no json here", {"nse:1"}) == {}


# --------------------------------------------------------------------------------------
# The service, with fakes
# --------------------------------------------------------------------------------------

MONDAY = date(2026, 9, 21)


class MemoryStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, date], Any] = {}

    async def get(self, kind: str, day: date) -> Any | None:
        return self.rows.get((kind, day))

    async def latest(
        self, kind: str, *, on_or_before: date | None = None
    ) -> tuple[date, Any] | None:
        days = sorted(
            d for k, d in self.rows if k == kind and (on_or_before is None or d <= on_or_before)
        )
        return None if not days else (days[-1], self.rows[(kind, days[-1])])

    async def history(self, kind: str, limit: int) -> list[tuple[date, Any]]:
        days = sorted((d for k, d in self.rows if k == kind), reverse=True)[:limit]
        return [(d, self.rows[(kind, d)]) for d in days]

    async def put(self, kind: str, day: date, payload: Any) -> None:
        self.rows[(kind, day)] = json.loads(json.dumps(payload, default=str))

    async def commit(self) -> None:
        return None


class FakeNse:
    def __init__(self, announcements: list[dict[str, Any]]) -> None:
        self.announcements = announcements
        self.calls: list[str] = []

    async def fetch_optional(self, paths: list[str]) -> dict[str, Any]:
        self.calls.extend(paths)
        out: dict[str, Any] = {}
        for path in paths:
            if path.startswith("/api/corporate-announcements"):
                out[path] = self.announcements
            elif path == "/api/event-calendar":
                out[path] = [
                    {
                        "symbol": "BBB",
                        "date": "21-Sep-2026",
                        "purpose": "Financial Results",
                        "bm_desc": "Q2",
                    }
                ]
            elif path.startswith("/api/corporates-corporateActions"):
                out[path] = []
            elif path.startswith("/api/snapshot-capital-market-largedeal"):
                out[path] = {"as_on_date": "18-Sep-2026"}
            else:
                out[path] = {"data": []}
        return out

    async def fo_ban_list(self) -> str | None:
        return "Securities in Ban For Trade Date 21-SEP-2026:\n1,CCC\n"


class FakeYahoo:
    def __init__(self, symbols: list[str]) -> None:
        self.symbols = symbols
        self.closing: dict[str, float] = {}
        self.as_of = int(datetime.combine(MONDAY, time(15, 30), IST).timestamp())

    async def closes_batch(
        self, symbols: list[str], *, range_: str = "3mo"
    ) -> dict[str, list[tuple[date, float]]]:
        out = {}
        for symbol in symbols:
            day = MONDAY - timedelta(days=60)
            series = []
            price = 100.0
            flip = 1
            while day < MONDAY:
                if day.weekday() < 5:
                    price *= 1 + flip * 0.01
                    flip = -flip
                    series.append((day, price))
                day += timedelta(days=1)
            out[symbol] = series
        return out

    async def quotes(self, symbols: list[str]) -> dict[str, Quote | None]:
        out: dict[str, Quote | None] = {}
        for symbol in symbols:
            change = self.closing.get(symbol.removesuffix(".NS"), 0.2)
            out[symbol] = Quote(
                symbol,
                f"{symbol} Ltd",
                100 * (1 + change / 100),
                100.0,
                None,
                None,
                150.0,
                50.0,
                None,
                self.as_of,
            )
        return out


class FakeNews:
    async def fetch_all(self) -> list[tuple[str, str]]:
        return [("Test Wire", RSS)]


def _preopen(day: date, gaps: dict[str, float]) -> dict[str, Any]:
    return {
        "timestamp": f"{day.strftime('%d-%b-%Y')} 09:08:30",
        "data": [
            {
                "metadata": {
                    "symbol": symbol,
                    "iep": 100 + gap,
                    "previousClose": 100,
                    "pChange": gap,
                    "marketCap": 1e5,
                },
                "detail": {
                    "preOpenMarket": {
                        "totalBuyQuantity": 900 if gap > 0 else 100,
                        "totalSellQuantity": 100 if gap > 0 else 900,
                    }
                },
            }
            for symbol, gap in gaps.items()
        ],
    }


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> tuple[MoversService, MemoryStore, FakeYahoo, FakeNse]:
    symbols = ["AAA", "BBB", "CCC", "DDD"]
    store = MemoryStore()
    store.rows[(KIND_PREOPEN, MONDAY)] = _preopen(
        MONDAY, {"AAA": 4.5, "BBB": 0.3, "CCC": -0.2, "DDD": 0.1}
    )
    nse = FakeNse(
        [
            _announcement(
                "AAA",
                "Outcome of Board Meeting",
                "Approved unaudited financial results",
                "2026-09-18 18:30:00",
                "11",
            ),
            _announcement(
                "DDD", "Trading Window", "Closure of trading window", "2026-09-19 10:00:00", "12"
            ),
        ]
    )
    yahoo = FakeYahoo(symbols)
    service = MoversService(store, nse=nse, yahoo=yahoo, news=FakeNews())  # type: ignore[arg-type]
    monkeypatch.setattr(
        movers_module, "ist_now", lambda: datetime.combine(MONDAY, time(9, 20), IST)
    )
    return service, store, yahoo, nse


async def test_forecast_ranks_the_gapping_stock_with_results_first(world: Any) -> None:
    service, store, _, _ = world
    await service.collect_filings(MONDAY)
    await service.collect_events(MONDAY)
    overnight = await service.build_forecast(MONDAY, "overnight")
    opening = await service.build_forecast(MONDAY, "opening")
    assert overnight is not None and opening is not None
    top = opening["stocks"][0]
    assert top["symbol"] == "AAA"
    assert top["direction"] == "up" and top["direction_confidence"] == "high"
    assert any("Pre-open gap +4.5%" in r["text"] for r in top["reasons"])
    assert any("Results" in r["text"] for r in top["reasons"])
    assert top["threshold_pct"] == 3.0
    by_symbol = {row["symbol"]: row for row in opening["stocks"]}
    assert by_symbol["CCC"]["flags"]["ban"] is True
    assert by_symbol["BBB"]["flags"]["results"] is True  # results due today, from the calendar
    # The overnight stage has no gap, so its AAA probability is lower.
    over_aaa = next(r for r in overnight["stocks"] if r["symbol"] == "AAA")
    assert over_aaa["probability"] < top["probability"]
    assert store.rows[(KIND_SAMPLES, MONDAY)]["has_gap"] is True


async def test_evaluation_grades_on_the_close_and_labels_the_samples(world: Any) -> None:
    service, store, yahoo, _ = world
    await service.collect_filings(MONDAY)
    await service.build_forecast(MONDAY, "opening")
    yahoo.closing = {"AAA": 6.2, "BBB": -0.4, "CCC": 3.4, "DDD": 0.1}
    grades = await service.evaluate(MONDAY)
    assert grades is not None
    opening = grades["opening"]
    assert opening["majors"] == 2 and opening["hits"] == 2
    outcome = store.rows[(KIND_OUTCOME, MONDAY)]
    assert outcome["stocks"]["AAA"] == [6.2, True]
    assert store.rows[(KIND_SAMPLES, MONDAY)]["outcomes"]["BBB"][1] is False
    model = await service.recalibrate(MONDAY)
    assert model is not None and store.rows[(KIND_MODEL, MONDAY)]["samples"]["opening"] == 4


async def test_no_grade_on_a_day_that_did_not_trade(world: Any) -> None:
    service, _, yahoo, _ = world
    await service.build_forecast(MONDAY, "opening")
    yahoo.as_of = int(datetime.combine(MONDAY - timedelta(days=3), time(15, 30), IST).timestamp())
    assert await service.evaluate(MONDAY) is None


async def test_news_is_collected_and_tagged(world: Any) -> None:
    service, store, _, _ = world
    store.rows[(KIND_CATALYSTS, MONDAY)] = {
        "items": [{"id": "x", "symbol": "AAA", "company": "HDFC Bank Limited"}]
    }
    tagged = await service.collect_news(MONDAY)
    assert tagged == 3
    payload = await service.news(MONDAY, tagged_only=True)
    assert [item["symbols"] for item in payload["items"]] == [["AAA"]]


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set_if_absent(self, key: str, *, ttl_seconds: int) -> bool:
        if key in self.values:
            return False
        self.values[key] = "1"
        return True

    async def get_str(self, key: str) -> str | None:
        return self.values.get(key)

    async def set_str(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.values[key] = value


async def test_alerts_only_for_fresh_high_impact_filings_and_capped(
    world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _, _, nse = world
    now = datetime.combine(MONDAY, time(11, 0), IST)
    monkeypatch.setattr(movers_module, "ist_now", lambda: now)
    nse.announcements = [
        _announcement(
            sym,
            "Bagging/Receiving of orders/contracts",
            "Order worth Rs 500 crore",
            "2026-09-21 10:45:00",
            f"o{i}",
        )
        for i, sym in enumerate(["AAA", "BBB", "CCC", "DDD"] * 5)
    ] + [
        _announcement(
            "AAA",
            "Bagging/Receiving of orders/contracts",
            "Old order worth Rs 5 crore",
            "2026-09-19 10:00:00",
            "old",
        ),
        _announcement(
            "BBB", "Trading Window", "Closure of trading window", "2026-09-21 10:50:00", "tw"
        ),
    ]
    sent: list[Catalyst] = []

    async def sink(items: list[Catalyst]) -> None:
        sent.extend(items)

    redis = FakeRedis()
    await service.scheduled_tick(redis, alert=sink)  # type: ignore[arg-type]
    assert len(sent) == movers_module.ALERTS_PER_DAY
    assert all(item.category == "order_win" and item.id != "nse:old" for item in sent)
    # Throttled: a second tick in the same window fetches nothing new.
    calls = len(nse.calls)
    await service.scheduled_tick(redis, alert=sink)  # type: ignore[arg-type]
    assert len(nse.calls) == calls


async def test_nothing_runs_at_the_weekend(world: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    service, _, _, nse = world
    monkeypatch.setattr(movers_module, "ist_now", lambda: datetime(2026, 9, 19, 9, 30, tzinfo=IST))
    await service.scheduled_tick(FakeRedis())  # type: ignore[arg-type]
    assert nse.calls == []


async def test_backtest_replays_real_shaped_history_and_fits(world: Any) -> None:
    service, store, yahoo, nse = world
    rng = random.Random(3)
    days = [MONDAY - timedelta(days=n) for n in range(130, 0, -1)]
    days = [d for d in days if d.weekday() < 5]

    async def bars(symbol: str, *, range_: str = "6mo") -> list[DailyBar]:
        price = 100.0
        out = []
        for day in days:
            gap = rng.gauss(0, 0.6)
            move = gap + rng.gauss(0, 1.0)
            opened = price * (1 + gap / 100)
            closed = price * (1 + move / 100)
            out.append(DailyBar(day, opened, max(opened, closed), min(opened, closed), closed))
            price = closed
        return out

    yahoo.daily_bars = bars  # type: ignore[method-assign]
    nse.announcements = []
    report = await service.backtest(days=40)
    assert report["sessions"] == 40
    assert report["test"] is not None and report["train"] is not None
    assert set(report["stages"]) == {"overnight", "opening"}
    assert report["stages"]["opening"]["fitted"]["summary"]["days"] == 12
    assert (KIND_MODEL, MONDAY) in store.rows
    assert all(kind != KIND_FORECAST["opening"] for kind, _ in store.rows)


def test_stop_loss_is_not_bad_news_and_quote_pages_are_not_news() -> None:
    from algo_platform.modules.market_insights.domain.catalysts import headline_sentiment

    assert headline_sentiment("Top stocks to buy: HDFC Bank - targets, stop-loss") == 0
    feed = (
        '<?xml version="1.0"?><rss><channel>'
        "<item><title>SBI Funds Share Price Today, SBIFUNDS Share Price NSE</title></item>"
        "<item><title>Vedanta Share Price - Live NSE: VEDL Stock Price &amp; Chart</title></item>"
        "<item><title>Vedanta board approves demerger</title></item>"
        "</channel></rss>"
    )
    assert [h.title for h in parse_rss(feed, "x")] == ["Vedanta board approves demerger"]


async def test_filings_after_the_close_are_labelled_for_the_next_session(world: Any) -> None:
    service, _, _, nse = world
    nse.announcements = [
        _announcement(
            "AAA", "Press Release", "Order worth Rs 90 crore", "2026-09-21 11:00:00", "a"
        ),
        _announcement(
            "BBB", "Press Release", "Order worth Rs 90 crore", "2026-09-21 19:30:00", "b"
        ),
        _announcement(
            "CCC", "Press Release", "Order worth Rs 90 crore", "2026-09-19 10:00:00", "c"
        ),
    ]
    await service.collect_filings(MONDAY)
    sessions = {
        item["symbol"]: item["session"] for item in (await service.catalysts(MONDAY))["filings"]
    }
    assert sessions == {"AAA": "intraday", "BBB": "after_close", "CCC": "overnight"}


# --------------------------------------------------------------------------------------
# Morning briefing
# --------------------------------------------------------------------------------------


class Outbox:
    def __init__(self) -> None:
        self.sent: list[Any] = []

    async def send(self, message: Any) -> None:
        self.sent.append(message)


def _briefing(service: MoversService, store: MemoryStore) -> Any:
    from algo_platform.modules.market_insights.application.briefing import BriefingService

    return BriefingService(store, service)  # type: ignore[arg-type]


async def test_briefing_waits_for_the_auction_then_sends_once(world: Any) -> None:
    service, store, _, _ = world
    briefing = _briefing(service, store)
    at = lambda h, m: datetime.combine(MONDAY, time(h, m), IST)  # noqa: E731
    assert not await briefing.due(at(9, 5))  # before the send window
    assert not await briefing.due(at(9, 12))  # no opening forecast yet: wait
    assert await briefing.due(at(9, 31))  # stopped waiting: send the overnight one
    await service.build_forecast(MONDAY, "opening")
    assert await briefing.due(at(9, 12))
    outbox = Outbox()
    await briefing.send(
        MONDAY, recipients=["Owner@Example.com", "owner@example.com"], sender=outbox
    )
    assert [m.to for m in outbox.sent] == ["owner@example.com"]
    assert not await briefing.due(at(9, 15))  # already sent today
    assert not await briefing.due(datetime(2026, 9, 19, 9, 15, tzinfo=IST))  # Saturday


async def test_briefing_names_the_picks_filings_and_routine(world: Any) -> None:
    from algo_platform.shared.infrastructure.heartbeats import Heartbeat

    service, store, _, _ = world
    await service.collect_filings(MONDAY)
    await service.collect_events(MONDAY)
    await service.build_forecast(MONDAY, "opening")
    store.rows[(KIND_OUTCOME, date(2026, 9, 18))] = {
        "evaluated_at": "2026-09-18T16:15:00+05:30",
        "stocks": {},
        "grades": {
            "opening": {
                "top_k": 10,
                "hits": 4,
                "majors": 12,
                "universe": 210,
                "precision": 0.4,
                "base_rate": 0.06,
                "lift": 6.7,
                "direction_calls": 4,
                "direction_right": 3,
            }
        },
    }
    outbox = Outbox()
    payload = await _briefing(service, store).send(
        MONDAY,
        recipients=["owner@example.com"],
        sender=outbox,
        heartbeats=[Heartbeat("email", "E-mail worker", None, 60)],
        alerts_yesterday=2,
        delivery="console",
        console_url="https://algomatrics.in",
    )
    [message] = outbox.sent
    assert message.subject.startswith("AI-CIO briefing · Mon 21 Sep · watch AAA")
    for needle in (
        "4 of the top 10",
        "6.7x better",
        "AAA",
        "Results due today: BBB",
        "In F&O ban: CCC",
    ):
        assert needle in message.text, needle
    assert "E-mail worker · NO HEARTBEAT" in message.text
    assert "not configured on the server" in message.text
    assert "https://algomatrics.in/app/market-intelligence" in message.html
    assert payload["recipients"] == ["owner@example.com"]
    archive = await _briefing(service, store).archive()
    assert archive["dates"] == ["2026-09-21"] and archive["briefing"]["subject"] == message.subject


async def test_briefing_html_escapes_exchange_text(world: Any) -> None:
    service, store, _, nse = world
    nse.announcements = [
        _announcement(
            "AAA",
            "Bagging/Receiving of orders/contracts",
            "Order worth Rs 500 crore <script>alert(1)</script>",
            "2026-09-18 19:00:00",
            "x1",
        )
    ]
    await service.collect_filings(MONDAY)
    await service.build_forecast(MONDAY, "opening")
    briefing = await _briefing(service, store).build(MONDAY)
    assert "<script>" not in briefing.html
    assert "&lt;script&gt;" in briefing.html


def test_extra_recipients_are_merged_and_cleaned() -> None:
    from algo_platform.modules.market_insights.application.briefing import briefing_recipients

    assert briefing_recipients(["A@x.com"], "b@y.com; a@x.com , not-an-email,") == [
        "a@x.com",
        "b@y.com",
    ]
