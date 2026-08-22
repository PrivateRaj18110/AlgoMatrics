"""In-engine strategy runtime: loads code, feeds events, supervises callbacks."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import structlog
from algo_strategy_sdk.context import ParamValue
from algo_strategy_sdk.events import Candle, Tick
from algo_strategy_sdk.strategy import Strategy as SdkStrategy
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from algo_platform.modules.billing.application.service import SubscriptionService
from algo_platform.modules.instruments.application.directory import InstrumentDirectory
from algo_platform.modules.market_data.application.simulator import (
    TIMEFRAME_SECONDS,
)
from algo_platform.modules.risk.application.service import RiskService
from algo_platform.modules.strategies.builtin.registry import create_builtin, is_builtin
from algo_platform.modules.strategies.domain.strategies import RunState, StrategyRun
from algo_platform.modules.strategies.infrastructure.artifact_store import ArtifactStore
from algo_platform.modules.strategies.infrastructure.models import (
    StrategyLogModel,
    StrategyRunModel,
    StrategyVersionModel,
)
from algo_platform.modules.trading.application.order_service import OrderService
from algo_platform.modules.trading.domain.orders import OrderType, TimeInForce
from algo_platform.modules.trading.infrastructure.models import PositionModel
from algo_platform.shared.domain.errors import DomainError
from algo_platform.shared.domain.types import (
    DomainEvent,
    Side,
    StrategyRunId,
    utc_now,
)
from algo_platform.shared.infrastructure.outbox import enqueue_event
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway

logger = structlog.get_logger("strategy_runtime")

CALLBACK_TIMEOUT_SECONDS = 10.0


class EngineStrategyContext:
    """Concrete SDK context wired to platform services (capability-limited)."""

    def __init__(
        self,
        *,
        run: StrategyRun,
        session_factory: async_sessionmaker[AsyncSession],
        redis: RedisGateway,
        billing_factory: Any,
        symbol_to_instrument: dict[str, UUID],
    ) -> None:
        self._run = run
        self._session_factory = session_factory
        self._redis = redis
        self._billing_factory = billing_factory
        self._symbols = symbol_to_instrument
        self._state: dict[str, Any] = dict(run.stats.get("user_state", {}))
        self.orders_placed = 0
        self.signals_emitted = 0

    @property
    def now(self) -> datetime:
        return utc_now()

    @property
    def params(self) -> Mapping[str, ParamValue]:
        return {
            k: v for k, v in self._run.parameters.items() if isinstance(v, str | int | float | bool)
        }

    async def subscribe_ticks(self, *instruments: str) -> None:
        await self.log(
            "subscribe_ticks is fixed at run creation; requested: " + ", ".join(instruments),
            level="debug",
        )

    async def subscribe_candles(self, instrument: str, *timeframes: str) -> None:
        await self.log(
            f"subscribe_candles is fixed at run creation; requested {instrument} "
            + ",".join(timeframes),
            level="debug",
        )

    async def emit_signal(
        self,
        *,
        name: str,
        instrument: str,
        strength: Decimal,
        attributes: dict[str, str | int | float | bool] | None = None,
    ) -> None:
        self.signals_emitted += 1
        async with self._session_factory() as session:
            await enqueue_event(
                session,
                event=DomainEvent.new(
                    event_type="strategies.signal_generated.v1",
                    aggregate_id=self._run.id,
                    tenant_id=self._run.organization_id,
                ),
                aggregate_type="strategy_run",
                payload={
                    "run_id": str(self._run.id),
                    "signal": name,
                    "instrument": instrument,
                    "strength": str(strength),
                    "attributes": attributes or {},
                },
            )
            session.add(
                StrategyLogModel(
                    run_id=self._run.id,
                    organization_id=self._run.organization_id,
                    level="info",
                    message=f"signal {name} on {instrument} (strength {strength})",
                    context={"attributes": attributes or {}},
                    logged_at=utc_now(),
                )
            )
            await session.commit()

    async def request_order(
        self,
        *,
        instrument: str,
        side: str,
        quantity: Decimal,
        order_type: str = "market",
        limit_price: Decimal | None = None,
        stop_price: Decimal | None = None,
    ) -> str:
        instrument_id = self._symbols.get(instrument.upper())
        if instrument_id is None:
            await self.log(
                f"order rejected: instrument {instrument} not subscribed", level="warning"
            )
            return ""
        client_order_id = f"run-{str(self._run.id)[:8]}-{uuid4().hex[:12]}"
        async with self._session_factory() as session:
            billing: SubscriptionService = self._billing_factory(session)
            order_service = OrderService(
                session=session,
                redis=self._redis,
                billing=billing,
                risk=RiskService(session),
            )
            try:
                order = await order_service.place_order(
                    self._run.organization_id,
                    account_id=self._run.account_id,
                    instrument_id=instrument_id,
                    side=Side(side),
                    quantity=quantity,
                    order_type=OrderType(order_type),
                    time_in_force=TimeInForce.GTC,
                    limit_price=limit_price,
                    stop_price=stop_price,
                    client_order_id=client_order_id,
                    strategy_run_id=StrategyRunId(self._run.id),
                    source="strategy",
                )
                await session.commit()
            except DomainError as error:
                await session.rollback()
                await self.log(f"order rejected: {error.message}", level="warning")
                return ""
        self.orders_placed += 1
        await self.log(f"{side} {quantity} {instrument} ({order_type}) -> {order.status.value}")
        return client_order_id

    async def cancel_order(self, client_order_id: str) -> None:
        from algo_platform.modules.trading.infrastructure.repositories import (
            SqlOrderRepository,
        )

        async with self._session_factory() as session:
            repo = SqlOrderRepository(session)
            order = await repo.get_by_client_order_id(self._run.account_id, client_order_id)
            if order is None:
                return
            billing: SubscriptionService = self._billing_factory(session)
            order_service = OrderService(
                session=session,
                redis=self._redis,
                billing=billing,
                risk=RiskService(session),
            )
            try:
                await order_service.cancel_order(self._run.organization_id, order.id)
                await session.commit()
            except DomainError as error:
                await session.rollback()
                await self.log(f"cancel failed: {error.message}", level="warning")

    async def get_position(self, instrument: str) -> Decimal:
        instrument_id = self._symbols.get(instrument.upper())
        if instrument_id is None:
            return Decimal("0")
        async with self._session_factory() as session:
            result = await session.execute(
                select(PositionModel.quantity).where(
                    PositionModel.account_id == self._run.account_id,
                    PositionModel.instrument_id == instrument_id,
                )
            )
            value = result.scalar_one_or_none()
            return Decimal(str(value)) if value is not None else Decimal("0")

    async def log(self, message: str, *, level: str = "info") -> None:
        async with self._session_factory() as session:
            session.add(
                StrategyLogModel(
                    run_id=self._run.id,
                    organization_id=self._run.organization_id,
                    level=level if level in {"debug", "info", "warning", "error"} else "info",
                    message=message[:1000],
                    context={},
                    logged_at=utc_now(),
                )
            )
            await session.commit()

    def state_get(self, key: str, default: object = None) -> object:
        return self._state.get(key, default)

    async def state_set(self, key: str, value: object) -> None:
        self._state[key] = value

    def snapshot_state(self) -> dict[str, Any]:
        return dict(self._state)


def load_strategy_instance(
    *,
    entry_point: str,
    source: str,
    artifact_path: str | None,
    checksum: str,
    artifacts: ArtifactStore,
) -> SdkStrategy:
    if source == "builtin":
        if not is_builtin(entry_point):
            raise LookupError(f"builtin strategy missing: {entry_point}")
        return create_builtin(entry_point)
    if artifact_path is None:
        raise LookupError("uploaded strategy has no artifact")
    code = artifacts.load(artifact_path, expected_checksum=checksum)
    module = _module_from_source(code, module_name=f"user_strategy_{checksum[:12]}")
    cls = getattr(module, entry_point, None)
    if cls is None or not isinstance(cls, type) or not issubclass(cls, SdkStrategy):
        raise LookupError(f"artifact does not define a Strategy subclass named {entry_point}")
    instance = cls()
    return instance


def _module_from_source(code: str, *, module_name: str) -> ModuleType:
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_loader(module_name, loader=None)
    if spec is None:
        raise LookupError("cannot create module spec for strategy artifact")
    module = importlib.util.module_from_spec(spec)
    exec(compile(code, module_name, "exec"), module.__dict__)  # noqa: S102 - AST-screened, checksum-pinned artifact
    sys.modules[module_name] = module
    return module


class StrategyRuntime:
    """One live strategy run inside the engine process."""

    def __init__(
        self,
        *,
        run: StrategyRun,
        strategy: SdkStrategy,
        context: EngineStrategyContext,
        instrument_symbols: dict[UUID, str],
        entry_point: str = "",
        source: str = "",
    ) -> None:
        self.run = run
        self._strategy = strategy
        self.context = context
        self._symbols = instrument_symbols
        self._candles: dict[UUID, _RuntimeCandleState] = {}
        self.failed_reason: str | None = None
        # Read-only identity used by the advisory market-intel shadow gate; the
        # runtime does not act on either.
        self.entry_point = entry_point
        self.source = source

    @property
    def run_id(self) -> UUID:
        return self.run.id

    @property
    def instrument_ids(self) -> list[UUID]:
        return list(self.run.instrument_ids)

    @property
    def instrument_symbols(self) -> list[str]:
        return list(self._symbols.values())

    async def start(self) -> None:
        await self._invoke(self._strategy.initialize(self.context))

    async def shutdown(self) -> None:
        await self._invoke(self._strategy.shutdown(self.context))

    async def on_tick(
        self, instrument_id: UUID, *, bid: Decimal, ask: Decimal, last: Decimal
    ) -> None:
        if self.run.state is not RunState.RUNNING or self.failed_reason:
            return
        symbol = self._symbols.get(instrument_id)
        if symbol is None:
            return
        if self.run.timeframe == "tick":
            tick = Tick(instrument=symbol, timestamp=utc_now(), bid=bid, ask=ask, last=last)
            await self._invoke(self._strategy.on_tick(tick, self.context))
            return
        state = self._candles.setdefault(instrument_id, _RuntimeCandleState(self.run.timeframe))
        completed = state.add(last)
        if completed is not None:
            candle = Candle(
                instrument=symbol,
                timeframe=self.run.timeframe,
                timestamp=completed["timestamp"],
                open=completed["open"],
                high=completed["high"],
                low=completed["low"],
                close=completed["close"],
                volume=completed["volume"],
            )
            await self._invoke(self._strategy.on_candle(candle, self.context))

    async def _invoke(self, coroutine: Any) -> None:
        try:
            await asyncio.wait_for(coroutine, timeout=CALLBACK_TIMEOUT_SECONDS)
        except TimeoutError:
            self.failed_reason = "strategy callback exceeded the deadline"
            logger.warning("runtime.callback_timeout", run_id=str(self.run.id))
        except Exception as error:
            self.failed_reason = f"{type(error).__name__}: {error}"
            logger.warning(
                "runtime.callback_failed",
                run_id=str(self.run.id),
                error=self.failed_reason,
            )

    def stats(self) -> dict[str, Any]:
        return {
            "orders_placed": self.context.orders_placed,
            "signals_emitted": self.context.signals_emitted,
            "user_state": self.context.snapshot_state(),
        }


class _RuntimeCandleState:
    def __init__(self, timeframe: str) -> None:
        self._seconds = TIMEFRAME_SECONDS[timeframe]
        self._bucket = -1
        self._open = Decimal("0")
        self._high = Decimal("0")
        self._low = Decimal("0")
        self._close = Decimal("0")
        self._volume = Decimal("0")

    def add(self, price: Decimal) -> dict[str, Any] | None:
        bucket = int(utc_now().timestamp()) // self._seconds * self._seconds
        completed: dict[str, Any] | None = None
        if self._bucket == -1:
            self._start(bucket, price)
            return None
        if bucket != self._bucket:
            completed = {
                "timestamp": datetime.fromtimestamp(self._bucket, tz=utc_now().tzinfo),
                "open": self._open,
                "high": self._high,
                "low": self._low,
                "close": self._close,
                "volume": self._volume,
            }
            self._start(bucket, price)
            return completed
        self._high = max(self._high, price)
        self._low = min(self._low, price)
        self._close = price
        self._volume += 1
        return completed

    def _start(self, bucket: int, price: Decimal) -> None:
        self._bucket = bucket
        self._open = price
        self._high = price
        self._low = price
        self._close = price
        self._volume = Decimal("1")


async def load_runtime(
    *,
    run_model: StrategyRunModel,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    redis: RedisGateway,
    billing_factory: Any,
    artifacts: ArtifactStore,
) -> StrategyRuntime:
    from algo_platform.modules.strategies.application.service import run_entity

    run = run_entity(run_model)
    version = await session.get(StrategyVersionModel, run.strategy_version_id)
    if version is None:
        raise LookupError("strategy version missing for run")
    strategy = load_strategy_instance(
        entry_point=version.entry_point,
        source=version.source,
        artifact_path=version.artifact_path,
        checksum=version.checksum,
        artifacts=artifacts,
    )
    directory = InstrumentDirectory(session)
    summaries = await directory.get_map(run.instrument_ids)
    symbol_by_id = {i: s.symbol for i, s in summaries.items()}
    id_by_symbol = {s.symbol.upper(): i for i, s in summaries.items()}
    context = EngineStrategyContext(
        run=run,
        session_factory=session_factory,
        redis=redis,
        billing_factory=billing_factory,
        symbol_to_instrument=id_by_symbol,
    )
    return StrategyRuntime(
        run=run,
        strategy=strategy,
        context=context,
        instrument_symbols=symbol_by_id,
        entry_point=version.entry_point,
        source=version.source,
    )
