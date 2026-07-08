from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from algo_platform.modules.market_data.application.simulator import (
    CandleAccumulator,
    SimInstrument,
    SimTick,
    SimulatedMarketDataSource,
)


def make_instrument(symbol: str = "TEST") -> SimInstrument:
    return SimInstrument(
        instrument_id=uuid4(),
        symbol=symbol,
        reference_price=Decimal("100"),
        tick_size=Decimal("0.05"),
    )


def test_same_seed_produces_identical_streams() -> None:
    instrument = make_instrument()
    source_a = SimulatedMarketDataSource([instrument], seed=99)
    source_b = SimulatedMarketDataSource([instrument], seed=99)
    for _ in range(50):
        ticks_a = source_a.next_ticks()
        ticks_b = source_b.next_ticks()
        assert ticks_a[0].last == ticks_b[0].last
        assert ticks_a[0].bid == ticks_b[0].bid


def test_different_seeds_diverge() -> None:
    instrument = make_instrument()
    source_a = SimulatedMarketDataSource([instrument], seed=1)
    source_b = SimulatedMarketDataSource([instrument], seed=2)
    diverged = any(
        source_a.next_ticks()[0].last != source_b.next_ticks()[0].last for _ in range(20)
    )
    assert diverged


def test_spread_is_positive_and_prices_positive() -> None:
    source = SimulatedMarketDataSource([make_instrument()], seed=5)
    for _ in range(100):
        tick = source.next_ticks()[0]
        assert tick.ask > tick.bid > 0
        assert tick.last > 0


def test_candle_accumulator_rolls_buckets() -> None:
    accumulator = CandleAccumulator(timeframe="1m")
    base = datetime(2026, 7, 3, 10, 0, 30, tzinfo=UTC)
    instrument_id = uuid4()

    def tick_at(moment: datetime, price: str) -> SimTick:
        return SimTick(
            instrument_id=instrument_id,
            symbol="TEST",
            bid=Decimal(price) - Decimal("0.01"),
            ask=Decimal(price) + Decimal("0.01"),
            last=Decimal(price),
            change_pct=Decimal("0"),
            timestamp=moment,
        )

    assert accumulator.add_tick(tick_at(base, "100")) is None
    assert accumulator.add_tick(tick_at(base.replace(second=45), "102")) is None
    completed = accumulator.add_tick(tick_at(base.replace(minute=1, second=5), "101"))
    assert completed is not None
    assert completed["open"] == "100"
    assert completed["high"] == "102"
    assert completed["close"] == "102"
