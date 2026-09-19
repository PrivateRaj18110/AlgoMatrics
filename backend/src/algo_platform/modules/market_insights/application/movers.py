"""AI-CIO movers radar: collect catalysts, forecast today's major movers, grade, learn.

Daily rhythm (IST, weekdays):

* 06:30-22:30  NSE filings every ~9 minutes (every 15 after the close); new
               high-impact filings on F&O stocks raise an in-app alert.
* 06:30-22:30  market headlines every 15 minutes.
* 07:30-09:05  event calendar, ex-dates, F&O ban list, bulk/block deals and
               open-interest spurts, every 30 minutes.
* 08:00-09:07  the *overnight* forecast, rebuilt as news arrives.
* 09:09-10:30  the *opening* forecast, once the pre-open auction is stored.
* 16:15-22:00  grade the day's forecasts on the close; refit the weights.

On first start with no backtest stored, a one-off job replays ~60 past sessions
(real filings and real prices) to fit the weights and measure an out-of-sample
hit rate before the first live forecast.

All state lives in ``market_snapshots`` rows (kind + trade date), so the history
of every forecast and every grade is kept.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Protocol

import structlog

from algo_platform.modules.market_insights.application.service import KIND_PREOPEN, ist_now
from algo_platform.modules.market_insights.domain.catalysts import (
    ALERT_IMPACT,
    IST,
    MARKET_CLOSE,
    MATERIAL_IMPACT,
    PREOPEN_FREEZE,
    Catalyst,
    Headline,
    ban_catalysts,
    impact_total,
    in_window,
    name_index,
    overnight_window,
    parse_announcements,
    parse_corporate_actions,
    parse_event_calendar,
    parse_large_deals,
    parse_oi_spurts,
    parse_rss,
    parse_secban,
    previous_session,
    tag_headlines,
)
from algo_platform.modules.market_insights.domain.move_model import (
    FEATURE_LABELS,
    FEATURES,
    MAJOR_TYPICAL_MULTIPLE,
    MIN_MAJOR_PCT,
    OPENING_ONLY,
    PRIOR_BIAS,
    PRIOR_WEIGHTS,
    STAGES,
    TOP_K,
    StageWeights,
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
    reasons,
    stage_vector,
    summarise,
)
from algo_platform.modules.market_insights.domain.premarket import parse_preopen
from algo_platform.modules.market_insights.domain.sectors import (
    FALLBACK_FO_UNIVERSE,
    sector_for,
    yahoo_symbol,
)
from algo_platform.modules.market_insights.infrastructure.news_feeds import NewsFeeds
from algo_platform.modules.market_insights.infrastructure.nse_client import (
    ANNOUNCEMENTS_PATH,
    CORPORATE_ACTIONS_PATH,
    EVENT_CALENDAR_PATH,
    LARGE_DEALS_PATH,
    OI_SPURTS_PATH,
    NseClient,
    NseUnavailable,
    nse_day,
)
from algo_platform.modules.market_insights.infrastructure.yahoo_batch import (
    DailyBar,
    YahooBatchQuotes,
    get_yahoo_batch,
)
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway

logger = structlog.get_logger(__name__)

KIND_CATALYSTS = "mv_catalysts"
KIND_EVENTS = "mv_events"
KIND_NEWS = "mv_news"
KIND_FORECAST = {"overnight": "mv_forecast_overnight", "opening": "mv_forecast_opening"}
KIND_SAMPLES = "mv_samples"
KIND_OUTCOME = "mv_outcome"
KIND_MODEL = "mv_model"
KIND_BACKTEST = "mv_backtest"

BACKTEST_DAYS = 60
#: Redis keys: an admin asks for a fresh backtest; the scheduler holds the lock while it runs.
BACKTEST_REQUEST_KEY = "mv:backtest:request"
BACKTEST_LOCK_KEY = "mv:backtest:lock"
TRAIN_FRACTION = 0.7
ALERTS_PER_DAY = 15
LEARN_LOOKBACK_DAYS = 160
_EVALUATE_FROM = time(16, 15)
THRESHOLD_RULE = (
    f"max({MIN_MAJOR_PCT:g}%, {MAJOR_TYPICAL_MULTIPLE:g}x the stock's typical daily move)"
)

DISCLAIMER = (
    "AI-CIO ranks how likely each F&O stock is to make a major move today from public "
    "filings, exchange data, headlines and prices. It is a research aid, graded daily in "
    "public below — not investment advice, and it never places orders."
)


class SnapshotStore(Protocol):
    async def get(self, kind: str, day: date) -> Any | None: ...

    async def latest(
        self, kind: str, *, on_or_before: date | None = None
    ) -> tuple[date, Any] | None: ...

    async def history(self, kind: str, limit: int) -> list[tuple[date, Any]]: ...

    async def put(self, kind: str, day: date, payload: Any) -> None: ...

    async def commit(self) -> None: ...


@dataclass(frozen=True, slots=True)
class FilingAssessment:
    impact: float
    direction: int
    note: str


class FilingReader(Protocol):
    """Optional second opinion on material filings (e.g. Claude)."""

    async def assess(self, filings: Sequence[Catalyst]) -> dict[str, FilingAssessment]: ...


AlertSink = Callable[[list[Catalyst]], Awaitable[None]]

#: Filing categories that count toward the "catalyst" feature. Ex-dates, bans and
#: deals have their own features or none; calendar results have "results".
_FILING_SOURCES = {"nse_filing"}


class MoversService:
    def __init__(
        self,
        store: SnapshotStore,
        *,
        nse: NseClient | None = None,
        yahoo: YahooBatchQuotes | None = None,
        news: NewsFeeds | None = None,
        reader: FilingReader | None = None,
    ) -> None:
        self._store = store
        self._nse = nse or NseClient()
        self._yahoo = yahoo or get_yahoo_batch()
        self._news = news or NewsFeeds()
        self._reader = reader

    # -- universe ---------------------------------------------------------------------

    async def universe(self, day: date) -> list[str]:
        row = await self._store.latest(KIND_PREOPEN, on_or_before=day)
        if row is not None:
            symbols = [stock.symbol for stock in parse_preopen(row[1]).stocks]
            if symbols:
                return symbols
        return list(FALLBACK_FO_UNIVERSE)

    # -- collection -------------------------------------------------------------------

    async def collect_filings(self, day: date) -> list[Catalyst]:
        """Filings since the previous session for the F&O universe; returns the new ones."""
        path = ANNOUNCEMENTS_PATH.format(start=nse_day(previous_session(day)), end=nse_day(day))
        rows = (await self._nse.fetch_optional([path])).get(path)
        if not isinstance(rows, list):
            raise NseUnavailable("announcements feed unavailable")
        parsed = parse_announcements(rows, set(await self.universe(day)))
        stored = await self._store.get(KIND_CATALYSTS, day) or {}
        known: dict[str, dict[str, Any]] = {item["id"]: item for item in stored.get("items", [])}
        new = [item for item in parsed if item.id not in known]
        if new and self._reader is not None:
            new = await self._refine(new)
        for item in new:
            known[item.id] = item.as_dict()
        items = sorted(known.values(), key=lambda item: item.get("at") or "", reverse=True)
        await self._store.put(
            KIND_CATALYSTS,
            day,
            {
                "items": items,
                "updated_at": ist_now().isoformat(),
                "ai_reader": self._reader is not None,
            },
        )
        return new

    async def _refine(self, filings: list[Catalyst]) -> list[Catalyst]:
        """Blend an AI reading of material filings with the rule-based one."""
        candidates = [item for item in filings if item.impact >= 0.3]
        if not candidates or self._reader is None:
            return filings
        try:
            assessments = await self._reader.assess(candidates)
        except Exception:
            logger.warning("movers.ai_reader_failed", filings=len(candidates))
            return filings
        refined: list[Catalyst] = []
        for item in filings:
            view = assessments.get(item.id)
            if view is None:
                refined.append(item)
                continue
            refined.append(
                dataclasses.replace(
                    item,
                    impact=round((item.impact + view.impact) / 2, 3),
                    direction=view.direction if view.direction else item.direction,
                    note=view.note or None,
                )
            )
        return refined

    async def collect_events(self, day: date) -> dict[str, Any]:
        """Calendar, ex-dates, ban list, large deals and OI spurts for ``day``."""
        paths = [EVENT_CALENDAR_PATH, CORPORATE_ACTIONS_PATH, LARGE_DEALS_PATH, OI_SPURTS_PATH]
        feeds = await self._nse.fetch_optional(paths)
        ban_text = await self._nse.fo_ban_list()
        universe = set(await self.universe(day))
        stored = await self._store.get(KIND_EVENTS, day) or {}
        previous: dict[str, list[dict[str, Any]]] = stored.get("by_source", {})
        by_source: dict[str, list[dict[str, Any]]] = dict(previous)

        calendar = feeds.get(EVENT_CALENDAR_PATH)
        if isinstance(calendar, list):
            by_source["calendar"] = [
                c.as_dict() for c in parse_event_calendar(calendar, universe, day)
            ]
        actions = feeds.get(CORPORATE_ACTIONS_PATH)
        if isinstance(actions, list):
            by_source["actions"] = [
                c.as_dict() for c in parse_corporate_actions(actions, universe, day)
            ]
        deals = feeds.get(LARGE_DEALS_PATH)
        if isinstance(deals, dict):
            by_source["deals"] = [
                c.as_dict()
                for c in parse_large_deals(deals, universe)
                if c.at is not None and c.at.date() == previous_session(day)
            ]
        if ban_text:
            ban_day, symbols = parse_secban(ban_text)
            if ban_day == day:
                by_source["ban"] = [c.as_dict() for c in ban_catalysts(symbols, universe, day)]
        oi_payload = feeds.get(OI_SPURTS_PATH)
        oi = (
            parse_oi_spurts(oi_payload, universe)
            if isinstance(oi_payload, dict)
            else stored.get("oi", {})
        )
        payload = {"by_source": by_source, "oi": oi, "updated_at": ist_now().isoformat()}
        await self._store.put(KIND_EVENTS, day, payload)
        return payload

    async def collect_news(self, day: date) -> int:
        feeds = await self._news.fetch_all()
        start = datetime.combine(previous_session(day), MARKET_CLOSE, IST) - timedelta(hours=3)
        headlines: list[Headline] = []
        for publisher, xml_text in feeds:
            headlines.extend(
                h for h in parse_rss(xml_text, publisher) if h.at is not None and h.at >= start
            )
        index = name_index(await self._companies(day))
        tagged = tag_headlines(headlines, index)
        stored = await self._store.get(KIND_NEWS, day) or {}
        known = {item["id"]: item for item in stored.get("items", [])}
        for item in tagged:
            known.setdefault(item.id, item.as_dict())
        items = sorted(known.values(), key=lambda item: item.get("at") or "", reverse=True)[:500]
        await self._store.put(
            KIND_NEWS,
            day,
            {"items": items, "feeds": len(feeds), "updated_at": ist_now().isoformat()},
        )
        return len(tagged)

    async def _companies(self, day: date) -> dict[str, str | None]:
        """Symbol → company name, from filings (as filed) and Yahoo (short names)."""
        universe = await self.universe(day)
        names: dict[str, str | None] = dict.fromkeys(universe)
        for when in (previous_session(day), day):
            for item in (await self._store.get(KIND_CATALYSTS, when) or {}).get("items", []):
                if item.get("company") and item.get("symbol") in names:
                    names[item["symbol"]] = item["company"]
        missing = [s for s, name in names.items() if not name]
        if missing:
            quotes = await self._yahoo.quotes([yahoo_symbol(s) for s in missing])
            for symbol in missing:
                quote = quotes.get(yahoo_symbol(symbol))
                if quote and quote.name:
                    names[symbol] = quote.name
        return names

    # -- forecast ---------------------------------------------------------------------

    async def _history(self, symbols: list[str], day: date) -> dict[str, list[float]]:
        by_yahoo = await self._yahoo.closes_batch([yahoo_symbol(s) for s in symbols])
        out: dict[str, list[float]] = {}
        for symbol in symbols:
            series = by_yahoo.get(yahoo_symbol(symbol)) or []
            out[symbol] = [close for when, close in series if when < day]
        return out

    async def _day_catalysts(self, day: date) -> tuple[list[Catalyst], list[Catalyst]]:
        """(overnight catalysts for ``day``, intraday filings on ``day``)."""
        window = overnight_window(day)
        seen: dict[str, Catalyst] = {}
        for when in (previous_session(day), day):
            for raw in (await self._store.get(KIND_CATALYSTS, when) or {}).get("items", []):
                item = Catalyst.from_dict(raw)
                seen.setdefault(item.id, item)
        overnight = [c for c in seen.values() if in_window(c.at, window)]
        intraday = [
            c
            for c in seen.values()
            if c.at is not None and window[1] < c.at <= datetime.combine(day, MARKET_CLOSE, IST)
        ]
        events = await self._store.get(KIND_EVENTS, day) or {}
        for items in (events.get("by_source") or {}).values():
            overnight.extend(Catalyst.from_dict(raw) for raw in items)
        return overnight, intraday

    async def model(self) -> tuple[dict[str, StageWeights], dict[str, Any]]:
        row = await self._store.latest(KIND_MODEL)
        if row is None:
            return prior_model(), {"source": "prior", "version": "prior", "fitted_at": None}
        fitted_on, payload = row
        stages = {stage: StageWeights.from_dict(payload["stages"][stage]) for stage in STAGES}
        return stages, {
            "source": "fitted",
            "version": payload.get("version"),
            "fitted_at": payload.get("fitted_at"),
            "samples": payload.get("samples"),
            "days": payload.get("days"),
            "fitted_on": fitted_on.isoformat(),
        }

    async def build_forecast(self, day: date, stage: str) -> dict[str, Any] | None:
        universe = await self.universe(day)
        preopen: dict[str, Any] = {}
        if stage == "opening":
            snapshot = await self._store.get(KIND_PREOPEN, day)
            if snapshot is None:
                return None
            preopen = {stock.symbol: stock for stock in parse_preopen(snapshot).stocks}
            universe = list(preopen) or universe
        closes = await self._history(universe, day)
        quotes = await self._yahoo.quotes([yahoo_symbol(s) for s in universe])
        overnight, _ = await self._day_catalysts(day)
        by_symbol: dict[str, list[Catalyst]] = defaultdict(list)
        for item in overnight:
            by_symbol[item.symbol].append(item)
        news_items = (await self._store.get(KIND_NEWS, day) or {}).get("items", [])
        window = overnight_window(day)
        news_count: dict[str, int] = defaultdict(int)
        news_mood: dict[str, int] = defaultdict(int)
        for raw in news_items:
            at = datetime.fromisoformat(raw["at"]) if raw.get("at") else None
            if at is None or not (window[0] < at <= max(window[1], ist_now())):
                continue
            for symbol in raw.get("symbols") or []:
                news_count[symbol] += 1
                news_mood[symbol] += int(raw.get("sentiment") or 0)
        oi = (await self._store.get(KIND_EVENTS, day) or {}).get("oi", {})
        models, meta = await self.model()
        weights = models[stage]

        rows: list[dict[str, Any]] = []
        samples: list[list[Any]] = []
        for symbol in universe:
            quote = quotes.get(yahoo_symbol(symbol))
            stats = history_stats(
                closes.get(symbol) or [],
                year_high=quote.year_high if quote else None,
                year_low=quote.year_low if quote else None,
            )
            if stats is None:
                continue
            pre = preopen.get(symbol)
            items = sorted(by_symbol.get(symbol, []), key=lambda c: -c.impact)
            filings = [c for c in items if c.source in _FILING_SOURCES]
            results_filing = next((c for c in filings if c.category == "results"), None)
            results_today = next((c for c in items if c.category == "results_today"), None)
            inputs = StockInputs(
                symbol=symbol,
                stats=stats,
                gap_pct=round(pre.change_pct, 3) if pre else None,
                imbalance=round(pre.imbalance, 3) if pre else None,
                catalyst_impact=impact_total(c.impact for c in filings),
                results=results_filing is not None or results_today is not None,
                news_count=news_count.get(symbol, 0),
                oi_change_pct=oi.get(symbol),
                in_ban=any(c.category == "fo_ban" for c in items),
                large_deal=any(c.category == "large_deal" for c in items),
            )
            features = feature_vector(inputs)
            probability = weights.probability(stage_vector(features, stage))
            lean = sum(c.direction * c.impact for c in items if c.category not in {"fo_ban"})
            call = direction_call(
                gap_pct=inputs.gap_pct,
                imbalance=inputs.imbalance,
                catalyst_direction=lean,
                news_sentiment=news_mood.get(symbol, 0),
            )
            rows.append(
                {
                    "symbol": symbol,
                    "sector": sector_for(symbol),
                    "probability": round(probability, 4),
                    "direction": call.direction,
                    "direction_basis": call.basis,
                    "direction_confidence": call.confidence,
                    "gap_pct": inputs.gap_pct,
                    "imbalance": inputs.imbalance,
                    "typical_move_pct": stats.typical_move,
                    "threshold_pct": major_threshold(stats.typical_move),
                    "prev_change_pct": stats.prev_change,
                    "last_close": stats.last_close,
                    "news_count": inputs.news_count,
                    "oi_change_pct": inputs.oi_change_pct,
                    "reasons": reasons(
                        inputs,
                        features,
                        weights,
                        stage,
                        catalyst_labels=[c.label for c in filings if c.impact >= 0.3][:3],
                        results_label=(
                            "Results filed overnight"
                            if results_filing
                            else "Results due today"
                            if results_today
                            else None
                        ),
                    ),
                    "catalysts": [
                        c.as_dict()
                        for c in items
                        if c.impact >= 0.15 or c.category == "ex_adjustment"
                    ][:4],
                    "flags": {
                        "results": inputs.results,
                        "ban": inputs.in_ban,
                        "ex_adjustment": any(c.category == "ex_adjustment" for c in items),
                    },
                }
            )
            samples.append(
                [
                    symbol,
                    [round(v, 4) for v in stage_vector(features, "opening")],
                    stats.typical_move,
                ]
            )
        rows.sort(key=lambda row: -row["probability"])
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank
        payload = {
            "stage": stage,
            "trade_date": day.isoformat(),
            "generated_at": ist_now().isoformat(),
            "model": meta,
            "universe": len(rows),
            "expected_majors": round(sum(row["probability"] for row in rows), 1),
            "threshold_rule": THRESHOLD_RULE,
            "stocks": rows,
        }
        await self._store.put(KIND_FORECAST[stage], day, payload)
        existing = await self._store.get(KIND_SAMPLES, day)
        if stage == "opening" or existing is None or not existing.get("has_gap"):
            await self._store.put(
                KIND_SAMPLES,
                day,
                {"source": "live", "has_gap": stage == "opening", "rows": samples},
            )
        return payload

    # -- grading and learning -------------------------------------------------------------

    async def evaluate(self, day: date) -> dict[str, Any] | None:
        """Grade ``day``'s forecasts on the close. None when the day did not trade (yet)."""
        forecasts = {stage: await self._store.get(KIND_FORECAST[stage], day) for stage in STAGES}
        reference = forecasts["opening"] or forecasts["overnight"]
        if reference is None:
            return None
        symbols = [row["symbol"] for row in reference["stocks"]]
        quotes = await self._yahoo.quotes([yahoo_symbol(s) for s in symbols])

        def traded_today(quote: Any) -> bool:
            return (
                bool(quote and quote.as_of)
                and datetime.fromtimestamp(int(quote.as_of), IST).date() == day
            )

        live = [q for q in quotes.values() if traded_today(q)]
        if len(live) < 0.5 * len(symbols):
            return None
        outcomes: dict[str, tuple[bool, float]] = {}
        for row in reference["stocks"]:
            quote = quotes.get(yahoo_symbol(row["symbol"]))
            if not traded_today(quote) or quote is None or quote.change_pct is None:
                continue
            if (row.get("flags") or {}).get("ex_adjustment"):
                continue  # a bonus/split ex-date reprices the stock mechanically
            change = float(quote.change_pct)
            outcomes[row["symbol"]] = (abs(change) >= float(row["threshold_pct"]), change)
        grades: dict[str, Any] = {}
        probabilities: dict[str, list[float | None]] = {}
        for index, stage in enumerate(STAGES):
            payload = forecasts[stage]
            if not payload:
                continue
            grades[stage] = grade_day(
                [(r["symbol"], float(r["probability"]), r["direction"]) for r in payload["stocks"]],
                outcomes,
            ).as_dict()
            for row in payload["stocks"]:
                pair = probabilities.setdefault(row["symbol"], [None, None])
                pair[index] = row["probability"]
        await self._store.put(
            KIND_OUTCOME,
            day,
            {
                "evaluated_at": ist_now().isoformat(),
                "stocks": {s: [round(change, 3), major] for s, (major, change) in outcomes.items()},
                "grades": grades,
                "probabilities": probabilities,
            },
        )
        samples = await self._store.get(KIND_SAMPLES, day)
        if samples is not None:
            samples["outcomes"] = {
                s: [round(change, 3), major] for s, (major, change) in outcomes.items()
            }
            await self._store.put(KIND_SAMPLES, day, samples)
        return grades

    async def recalibrate(self, on: date) -> dict[str, Any] | None:
        """Refit both stages on every graded sample (backtest + live) in the lookback."""
        history = await self._store.history(KIND_SAMPLES, LEARN_LOOKBACK_DAYS)
        data: dict[str, tuple[list[list[float]], list[int]]] = {stage: ([], []) for stage in STAGES}
        sources: dict[str, int] = defaultdict(int)
        days = 0
        for _, payload in history:
            outcomes = payload.get("outcomes")
            if not outcomes:
                continue
            days += 1
            sources[payload.get("source", "live")] += 1
            for symbol, vector, _typical in payload.get("rows", []):
                outcome = outcomes.get(symbol)
                if outcome is None:
                    continue
                features = dict(zip(FEATURES, vector, strict=True))
                label = int(bool(outcome[1]))
                x, y = data["overnight"]
                x.append(stage_vector(features, "overnight"))
                y.append(label)
                if payload.get("has_gap"):
                    x, y = data["opening"]
                    x.append(stage_vector(features, "opening"))
                    y.append(label)
        if days == 0:
            return None
        priors = prior_model()
        stages: dict[str, Any] = {}
        for stage in STAGES:
            rows, labels = data[stage]
            weights = await asyncio.to_thread(fit_logistic, rows, labels, prior=priors[stage])
            stages[stage] = weights.as_dict()
        payload = {
            "version": f"{on.isoformat()}·{days}d",
            "fitted_at": ist_now().isoformat(),
            "days": days,
            "sources": dict(sources),
            "samples": {stage: len(data[stage][1]) for stage in STAGES},
            "stages": stages,
        }
        await self._store.put(KIND_MODEL, on, payload)
        return payload

    # -- backtest ---------------------------------------------------------------------------

    async def _bars(self, symbols: list[str]) -> dict[str, list[DailyBar]]:
        gate = asyncio.Semaphore(4)

        async def one(symbol: str) -> tuple[str, list[DailyBar]]:
            async with gate:
                bars = await self._yahoo.daily_bars(yahoo_symbol(symbol), range_="6mo")
                await asyncio.sleep(0.2)
                return symbol, bars

        return dict(await asyncio.gather(*(one(s) for s in symbols)))

    async def backtest(self, *, days: int = BACKTEST_DAYS) -> dict[str, Any]:
        """Replay past sessions with real filings and prices; fit, test out-of-sample, store."""
        today = ist_now().date()
        universe = await self.universe(today)
        bars = await self._bars(universe)
        calendar = sorted(
            {bar.day for series in bars.values() for bar in series if bar.day < today}
        )
        sessions = [
            d
            for d in calendar
            if sum(1 for s in bars.values() if any(b.day == d for b in s)) > len(bars) // 2
        ]
        sessions = sessions[-days:]
        if len(sessions) < 10:
            raise NseUnavailable("not enough price history for a backtest")

        filings: dict[str, list[Catalyst]] = defaultdict(list)
        first = previous_session(sessions[0])
        span = [first + timedelta(days=offset) for offset in range((sessions[-1] - first).days + 1)]
        universe_set = set(universe)
        for start in range(0, len(span), 15):
            chunk = span[start : start + 15]
            paths = [ANNOUNCEMENTS_PATH.format(start=nse_day(d), end=nse_day(d)) for d in chunk]
            feeds = await self._nse.fetch_optional(paths)
            for path in paths:
                announcements = feeds.get(path)
                if isinstance(announcements, list):
                    for item in parse_announcements(announcements, universe_set):
                        filings[item.symbol].append(item)
        seen: set[str] = set()
        for symbol in list(filings):
            unique = []
            for item in filings[symbol]:
                if item.id not in seen:
                    seen.add(item.id)
                    unique.append(item)
            filings[symbol] = unique

        per_day: list[tuple[date, dict[str, Any], dict[str, str], dict[str, str]]] = []
        for day in sessions:
            window = overnight_window(day)
            session_end = datetime.combine(day, MARKET_CLOSE, IST)
            rows: list[list[Any]] = []
            outcomes: dict[str, list[Any]] = {}
            directions: dict[str, dict[str, str]] = {"overnight": {}, "opening": {}}
            for symbol, series in bars.items():
                index = next((i for i, bar in enumerate(series) if bar.day == day), None)
                if index is None or index < 21:
                    continue
                prior = [bar.close for bar in series[:index]]
                stats = history_stats(prior)
                if stats is None or not prior[-1]:
                    continue
                bar = series[index]
                gap = (bar.open - prior[-1]) / prior[-1] * 100
                change = (bar.close - prior[-1]) / prior[-1] * 100
                overnight = [c for c in filings.get(symbol, []) if in_window(c.at, window)]
                # A results filing during the session was pre-announced (board-meeting
                # intimation), so the calendar would have flagged it that morning.
                results_due = any(
                    c.category == "results" and c.at is not None and window[1] < c.at <= session_end
                    for c in filings.get(symbol, [])
                )
                inputs = StockInputs(
                    symbol=symbol,
                    stats=stats,
                    gap_pct=gap,
                    catalyst_impact=impact_total(c.impact for c in overnight),
                    results=results_due or any(c.category == "results" for c in overnight),
                )
                features = feature_vector(inputs)
                rows.append(
                    [
                        symbol,
                        [round(v, 4) for v in stage_vector(features, "opening")],
                        stats.typical_move,
                    ]
                )
                outcomes[symbol] = [round(change, 3), is_major(change, stats.typical_move)]
                lean = sum(c.direction * c.impact for c in overnight)
                directions["opening"][symbol] = direction_call(
                    gap_pct=gap, imbalance=None, catalyst_direction=lean, news_sentiment=0
                ).direction
                directions["overnight"][symbol] = direction_call(
                    gap_pct=None, imbalance=None, catalyst_direction=lean, news_sentiment=0
                ).direction
            sample: dict[str, Any] = {
                "source": "backtest",
                "has_gap": True,
                "rows": rows,
                "outcomes": outcomes,
            }
            await self._store.put(KIND_SAMPLES, day, sample)
            per_day.append((day, sample, directions["overnight"], directions["opening"]))

        # Out-of-sample: fit on the earlier sessions, grade the later ones.
        cut = max(1, int(len(per_day) * TRAIN_FRACTION))
        train, test = per_day[:cut], per_day[cut:]
        priors = prior_model()
        report: dict[str, Any] = {}
        base_majors = sum(sum(1 for o in s["outcomes"].values() if o[1]) for _, s, _, _ in per_day)
        base_total = sum(len(s["outcomes"]) for _, s, _, _ in per_day)
        for stage in STAGES:
            x: list[list[float]] = []
            y: list[int] = []
            for _, sample, _, _ in train:
                for symbol, vector, _typical in sample["rows"]:
                    x.append(stage_vector(dict(zip(FEATURES, vector, strict=True)), stage))
                    y.append(int(bool(sample["outcomes"][symbol][1])))
            fitted = await asyncio.to_thread(fit_logistic, x, y, prior=priors[stage])
            stage_report: dict[str, Any] = {"weights_on_train": fitted.as_dict()}
            for label, weights in (("fitted", fitted), ("prior", priors[stage])):
                daily = []
                pairs: list[tuple[float, bool]] = []
                for day, sample, over_dirs, open_dirs in test:
                    dirs = open_dirs if stage == "opening" else over_dirs
                    predictions = []
                    for symbol, vector, _typical in sample["rows"]:
                        p = weights.probability(
                            stage_vector(dict(zip(FEATURES, vector, strict=True)), stage)
                        )
                        predictions.append((symbol, p, dirs.get(symbol, "either")))
                        pairs.append((p, bool(sample["outcomes"][symbol][1])))
                    outcome_map = {
                        s: (bool(o[1]), float(o[0])) for s, o in sample["outcomes"].items()
                    }
                    grade = grade_day(predictions, outcome_map).as_dict()
                    daily.append({"day": day.isoformat(), **grade})
                stage_report[label] = {
                    "summary": summarise(daily),
                    "daily": daily if label == "fitted" else [],
                }
                if label == "fitted":
                    stage_report["calibration"] = calibration(pairs)
            report[stage] = stage_report
        payload = {
            "ran_at": ist_now().isoformat(),
            "sessions": len(per_day),
            "train": [train[0][0].isoformat(), train[-1][0].isoformat()] if train else None,
            "test": [test[0][0].isoformat(), test[-1][0].isoformat()] if test else None,
            "universe": len(bars),
            "filings": sum(len(v) for v in filings.values()),
            "base_rate": round(base_majors / base_total, 4) if base_total else None,
            "stages": report,
            "limits": [
                "Uses today's F&O list for past sessions (survivorship).",
                "The open price stands in for the pre-open auction price; imbalance, news, "
                "open interest, ban list and deals have no history, so their weights stay "
                "at the prior.",
            ],
        }
        await self._store.put(KIND_BACKTEST, today, payload)
        await self.recalibrate(today)
        return payload

    # -- schedule ---------------------------------------------------------------------------

    async def scheduled_tick(self, redis: RedisGateway, alert: AlertSink | None = None) -> None:
        now = ist_now()
        if now.weekday() >= 5:
            return
        day = now.date()
        clock = now.time()

        async def due(key: str, every: int) -> bool:
            return await redis.set_if_absent(f"mv:tick:{key}", ttl_seconds=every)

        if time(6, 30) <= clock <= time(22, 30):
            if await due("filings", 540 if clock <= time(16, 0) else 900):
                try:
                    new = await self.collect_filings(day)
                except NseUnavailable as error:
                    logger.warning("movers.filings_failed", error=str(error))
                    new = []
                if alert is not None and new and clock >= time(7, 0):
                    await self._alert(redis, day, new, alert)
            if await due("news", 900):
                try:
                    await self.collect_news(day)
                except Exception:
                    logger.warning("movers.news_failed")
        if time(7, 30) <= clock <= time(9, 5) and await due("events", 1800):
            try:
                await self.collect_events(day)
            except NseUnavailable as error:
                logger.warning("movers.events_failed", error=str(error))
        if time(8, 0) <= clock < PREOPEN_FREEZE and await due("overnight", 900):
            await self.build_forecast(day, "overnight")
        if time(9, 9) <= clock <= time(10, 30):
            done = f"mv:done:opening:{day.isoformat()}"
            if (
                await redis.get_str(done) is None
                and await self._store.get(KIND_PREOPEN, day) is not None
            ):
                if await self._store.get(KIND_FORECAST["overnight"], day) is None:
                    await self.build_forecast(day, "overnight")
                if await self.build_forecast(day, "opening") is not None:
                    await redis.set_str(done, "1", ttl_seconds=86_400)
        if _EVALUATE_FROM <= clock <= time(22, 0):
            done = f"mv:done:graded:{day.isoformat()}"
            if await redis.get_str(done) is None and await due("grade", 1200):
                grades = await self.evaluate(day)
                if grades is not None:
                    await self.recalibrate(day)
                    await redis.set_str(done, "1", ttl_seconds=86_400)

    async def _alert(
        self, redis: RedisGateway, day: date, new: list[Catalyst], alert: AlertSink
    ) -> None:
        cutoff = ist_now() - timedelta(hours=2)
        fresh = [c for c in new if c.impact >= ALERT_IMPACT and c.at is not None and c.at >= cutoff]
        if not fresh:
            return
        used = int(await redis.get_str(f"mv:alerts:{day.isoformat()}") or 0)
        room = max(0, ALERTS_PER_DAY - used)
        chosen = sorted(fresh, key=lambda c: -c.impact)[:room]
        if not chosen:
            return
        await redis.set_str(
            f"mv:alerts:{day.isoformat()}", str(used + len(chosen)), ttl_seconds=3 * 86_400
        )
        await alert(chosen)

    async def backtest_needed(self) -> bool:
        return await self._store.latest(KIND_BACKTEST) is None

    # -- read side ------------------------------------------------------------------------

    async def movers(self, day: date | None = None) -> dict[str, Any]:
        target = day or ist_now().date()
        forecasts = {stage: await self._store.get(KIND_FORECAST[stage], target) for stage in STAGES}
        if day is None and not any(forecasts.values()):
            latest = await self._store.latest(KIND_FORECAST["opening"]) or await self._store.latest(
                KIND_FORECAST["overnight"]
            )
            if latest is not None:
                target = latest[0]
                forecasts = {
                    stage: await self._store.get(KIND_FORECAST[stage], target) for stage in STAGES
                }
        chosen = forecasts["opening"] or forecasts["overnight"]
        _, meta = await self.model()
        dates = sorted(
            {
                when.isoformat()
                for stage in STAGES
                for when, _ in await self._store.history(KIND_FORECAST[stage], 30)
            },
            reverse=True,
        )
        if chosen is None:
            return {"available": False, "model": meta, "dates": dates, "disclaimer": DISCLAIMER}
        outcome = await self._store.get(KIND_OUTCOME, target)
        _, intraday = await self._day_catalysts(target)
        return {
            "available": True,
            "trade_date": target.isoformat(),
            "stage": chosen["stage"],
            "stale": target != ist_now().date(),
            "forecast": chosen,
            "overnight_available": forecasts["overnight"] is not None,
            "outcome": outcome,
            "intraday": [
                c.as_dict()
                for c in sorted(intraday, key=lambda c: -c.impact)
                if c.impact >= MATERIAL_IMPACT
            ][:25],
            "model": meta,
            "dates": dates,
            "disclaimer": DISCLAIMER,
        }

    async def catalysts(
        self, day: date | None = None, *, min_impact: float = 0.15
    ) -> dict[str, Any]:
        target = day or ist_now().date()
        items: dict[str, dict[str, Any]] = {}
        for when in (previous_session(target), target):
            for raw in (await self._store.get(KIND_CATALYSTS, when) or {}).get("items", []):
                items.setdefault(raw["id"], raw)
        window = overnight_window(target)
        session_close = datetime.combine(target, MARKET_CLOSE, IST)
        events = await self._store.get(KIND_EVENTS, target) or {}
        event_items = [raw for group in (events.get("by_source") or {}).values() for raw in group]
        filings = []
        for raw in items.values():
            at = datetime.fromisoformat(raw["at"]) if raw.get("at") else None
            if at is None or at <= window[0]:
                continue
            if float(raw.get("impact") or 0) < min_impact:
                continue
            session = (
                "overnight"
                if at <= window[1]
                else "intraday"
                if at <= session_close
                else "after_close"
            )
            filings.append({**raw, "session": session})
        filings.sort(key=lambda raw: raw.get("at") or "", reverse=True)
        stored = await self._store.get(KIND_CATALYSTS, target) or {}
        return {
            "trade_date": target.isoformat(),
            "filings": filings[:300],
            "events": sorted(
                event_items,
                key=lambda raw: (-float(raw.get("impact") or 0), raw.get("symbol") or ""),
            ),
            "oi_spurts": events.get("oi", {}),
            "updated_at": stored.get("updated_at"),
            "events_updated_at": events.get("updated_at"),
            "ai_reader": bool(stored.get("ai_reader")),
        }

    async def news(self, day: date | None = None, *, tagged_only: bool = False) -> dict[str, Any]:
        target = day or ist_now().date()
        stored = await self._store.get(KIND_NEWS, target) or {}
        items = stored.get("items", [])
        if tagged_only:
            items = [item for item in items if item.get("symbols")]
        return {
            "trade_date": target.isoformat(),
            "items": items[:200],
            "feeds": stored.get("feeds"),
            "updated_at": stored.get("updated_at"),
        }

    async def track_record(self) -> dict[str, Any]:
        outcomes = await self._store.history(KIND_OUTCOME, 60)
        daily: dict[str, list[dict[str, Any]]] = {stage: [] for stage in STAGES}
        pairs: list[tuple[float, bool]] = []
        for when, payload in sorted(outcomes, key=lambda item: item[0]):
            for stage, grade in (payload.get("grades") or {}).items():
                daily.setdefault(stage, []).append({"day": when.isoformat(), **grade})
            stocks = payload.get("stocks") or {}
            for symbol, probs in (payload.get("probabilities") or {}).items():
                if symbol in stocks and probs and probs[1] is not None:
                    pairs.append((float(probs[1]), bool(stocks[symbol][1])))
        models, meta = await self.model()
        backtest = await self._store.latest(KIND_BACKTEST)
        return {
            "live": {
                stage: {"summary": summarise(daily[stage][-20:]), "daily": daily[stage][-40:]}
                for stage in STAGES
            },
            "calibration": calibration(pairs),
            "backtest": None
            if backtest is None
            else {"ran_on": backtest[0].isoformat(), **backtest[1]},
            "model": {
                **meta,
                "features": [
                    {
                        "name": name,
                        "label": FEATURE_LABELS[name],
                        "opening_only": name in OPENING_ONLY,
                        "prior": {stage: PRIOR_WEIGHTS[name] for stage in STAGES},
                        "weight": {
                            stage: round(models[stage].weights[name], 4) for stage in STAGES
                        },
                    }
                    for name in FEATURES
                ],
                "bias": {stage: round(models[stage].bias, 4) for stage in STAGES},
                "prior_bias": PRIOR_BIAS,
                "top_k": TOP_K,
                "threshold_rule": THRESHOLD_RULE,
            },
            "disclaimer": DISCLAIMER,
        }
