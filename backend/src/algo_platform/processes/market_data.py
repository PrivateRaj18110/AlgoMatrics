"""Market-data process: generates/normalizes ticks and fans them out.

Publishes each tick to:
- Redis hash ``md:last`` (latest quote per instrument, read by the API);
- pub/sub channel ``md:ticks`` (fan-in consumed by the trading engine);
- pub/sub channel ``ticks:{instrument_id}`` (WebSocket subscribers);
and maintains rolling candle windows under ``md:candles:{id}:{tf}``.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

import structlog
from sqlalchemy import select

from algo_platform.config import get_settings
from algo_platform.modules.instruments.infrastructure.models import InstrumentModel
from algo_platform.modules.market_data.application.simulator import (
    TIMEFRAME_SECONDS,
    CandleAccumulator,
    SimInstrument,
    SimulatedMarketDataSource,
)
from algo_platform.shared.domain.types import utc_now
from algo_platform.shared.infrastructure.database import (
    create_engine,
    create_session_factory,
)
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway
from algo_platform.shared.infrastructure.telemetry import configure_logging

logger = structlog.get_logger("market_data")

LAST_PRICES_KEY = "md:last"
TICKS_CHANNEL = "md:ticks"
CANDLES_KEY_PREFIX = "md:candles"
CANDLE_WINDOW = 500
HEARTBEAT_KEY = "hb:market_data"


async def run() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, env=settings.app_env, service="algo-market-data")
    engine = create_engine(settings.database_url, pool_size=4)
    session_factory = create_session_factory(engine)
    redis = RedisGateway.from_url(settings.redis_url)

    async with session_factory() as session:
        rows = (
            (await session.execute(select(InstrumentModel).where(InstrumentModel.is_active)))
            .scalars()
            .all()
        )
        instruments = [
            SimInstrument(
                instrument_id=r.id,
                symbol=r.symbol,
                reference_price=r.reference_price,
                tick_size=r.tick_size,
            )
            for r in rows
        ]
    if not instruments:
        logger.warning("market_data.no_instruments_seeded")
    source = SimulatedMarketDataSource(instruments, seed=settings.market_data_seed)
    accumulators: dict[tuple[str, str], CandleAccumulator] = {}
    candle_cache: dict[tuple[str, str], list[dict[str, str]]] = {}

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)
    interval = settings.market_tick_interval_ms / 1000
    logger.info(
        "market_data.started",
        instruments=len(instruments),
        interval_ms=settings.market_tick_interval_ms,
        source=settings.market_data_source,
    )
    try:
        while not stop_event.is_set():
            started = asyncio.get_event_loop().time()
            ticks = source.next_ticks()
            for tick in ticks:
                payload = {
                    "channel": "ticks",
                    "instrument_id": str(tick.instrument_id),
                    "symbol": tick.symbol,
                    "bid": str(tick.bid),
                    "ask": str(tick.ask),
                    "last": str(tick.last),
                    "change_pct": str(tick.change_pct),
                    "timestamp": tick.timestamp.isoformat(),
                }
                await redis.hset_json(LAST_PRICES_KEY, str(tick.instrument_id), payload)
                await redis.publish_json(TICKS_CHANNEL, payload)
                await redis.publish_json(f"ticks:{tick.instrument_id}", payload)

                for timeframe in TIMEFRAME_SECONDS:
                    key = (str(tick.instrument_id), timeframe)
                    accumulator = accumulators.get(key)
                    if accumulator is None:
                        accumulator = CandleAccumulator(timeframe=timeframe)
                        accumulators[key] = accumulator
                    completed = accumulator.add_tick(tick)
                    if completed is not None:
                        window = candle_cache.setdefault(key, [])
                        window.append(completed)
                        del window[:-CANDLE_WINDOW]
                        await redis.set_json(
                            f"{CANDLES_KEY_PREFIX}:{key[0]}:{timeframe}",
                            {"candles": window},
                        )
                        await redis.publish_json(
                            "md:candles",
                            {
                                "instrument_id": key[0],
                                "timeframe": timeframe,
                                "candle": completed,
                            },
                        )
            await redis.set_str(HEARTBEAT_KEY, utc_now().isoformat(), ttl_seconds=120)
            elapsed = asyncio.get_event_loop().time() - started
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop_event.wait(), timeout=max(0.05, interval - elapsed))
    finally:
        await redis.close()
        await engine.dispose()
        logger.info("market_data.stopped")


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_event_loop()
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Windows event loop: fall back to KeyboardInterrupt handling.
            signal.signal(sig, lambda *_: stop_event.set())


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
