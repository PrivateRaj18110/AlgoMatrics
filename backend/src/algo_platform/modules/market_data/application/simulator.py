"""Deterministic simulated market-data source for paper trading.

Prices follow a seeded geometric-brownian random walk anchored to each
instrument's reference price. The same seed, instrument set, and date produce
an identical tick stream, which keeps paper fills reproducible. Live venue
feeds plug in behind the same ``MarketDataSource`` port later.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol
from uuid import UUID

from algo_platform.shared.domain.types import utc_now

_PRICE_QUANTUM = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class SimTick:
    instrument_id: UUID
    symbol: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    change_pct: Decimal
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class SimInstrument:
    instrument_id: UUID
    symbol: str
    reference_price: Decimal
    tick_size: Decimal


class MarketDataSource(Protocol):
    def next_ticks(self) -> list[SimTick]: ...


class SimulatedMarketDataSource:
    """Geometric brownian walk with per-instrument volatility and spread."""

    def __init__(
        self,
        instruments: list[SimInstrument],
        *,
        seed: int,
        annual_volatility: float = 0.35,
        ticks_per_day: int = 86_400,
    ) -> None:
        self._instruments = instruments
        self._day_key = utc_now().strftime("%Y%m%d")
        self._step_sigma = annual_volatility / math.sqrt(252 * ticks_per_day)
        self._rngs: dict[UUID, random.Random] = {}
        self._prices: dict[UUID, float] = {}
        self._opens: dict[UUID, float] = {}
        for instrument in instruments:
            instrument_seed = hash((seed, instrument.symbol, self._day_key)) & 0x7FFFFFFF
            rng = random.Random(instrument_seed)  # noqa: S311 - simulation, not crypto
            self._rngs[instrument.instrument_id] = rng
            start = float(instrument.reference_price)
            # Deterministic day-open offset so restarts stay aligned per day.
            start *= 1 + rng.uniform(-0.01, 0.01)
            self._prices[instrument.instrument_id] = start
            self._opens[instrument.instrument_id] = start

    def next_ticks(self) -> list[SimTick]:
        now = utc_now()
        ticks: list[SimTick] = []
        for instrument in self._instruments:
            rng = self._rngs[instrument.instrument_id]
            price = self._prices[instrument.instrument_id]
            drift = -0.5 * self._step_sigma**2
            shock = rng.gauss(0, self._step_sigma)
            price = max(price * math.exp(drift + shock), 0.0001)
            self._prices[instrument.instrument_id] = price

            spread_fraction = max(rng.uniform(0.0002, 0.0008), 1e-6)
            half_spread = price * spread_fraction / 2
            last = Decimal(str(round(price, 6))).quantize(_PRICE_QUANTUM, rounding=ROUND_HALF_UP)
            bid = Decimal(str(round(price - half_spread, 6))).quantize(
                _PRICE_QUANTUM, rounding=ROUND_HALF_UP
            )
            ask = Decimal(str(round(price + half_spread, 6))).quantize(
                _PRICE_QUANTUM, rounding=ROUND_HALF_UP
            )
            open_price = self._opens[instrument.instrument_id]
            change_pct = Decimal(str(round((price - open_price) / open_price * 100, 4)))
            ticks.append(
                SimTick(
                    instrument_id=instrument.instrument_id,
                    symbol=instrument.symbol,
                    bid=bid,
                    ask=ask,
                    last=last,
                    change_pct=change_pct,
                    timestamp=now,
                )
            )
        return ticks


TIMEFRAME_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}


@dataclass(slots=True)
class CandleAccumulator:
    """Builds OHLCV candles from ticks for one instrument+timeframe."""

    timeframe: str
    bucket_start: int = -1
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: Decimal = Decimal("0")

    def add_tick(self, tick: SimTick) -> dict[str, str] | None:
        """Feed a tick; returns the completed candle dict when a bucket closes."""
        seconds = TIMEFRAME_SECONDS[self.timeframe]
        bucket = int(tick.timestamp.timestamp()) // seconds * seconds
        completed: dict[str, str] | None = None
        if self.bucket_start == -1:
            self._start(bucket, tick)
            return None
        if bucket != self.bucket_start:
            completed = self.snapshot()
            self._start(bucket, tick)
            return completed
        self.high = max(self.high, tick.last)
        self.low = min(self.low, tick.last)
        self.close = tick.last
        self.volume += 1
        return completed

    def _start(self, bucket: int, tick: SimTick) -> None:
        self.bucket_start = bucket
        self.open = tick.last
        self.high = tick.last
        self.low = tick.last
        self.close = tick.last
        self.volume = Decimal("1")

    def snapshot(self) -> dict[str, str]:
        return {
            "timestamp": datetime.fromtimestamp(self.bucket_start, tz=utc_now().tzinfo).isoformat(),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": str(self.volume),
        }
