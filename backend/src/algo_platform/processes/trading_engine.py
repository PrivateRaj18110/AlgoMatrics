"""Trading-engine process: strategy runtimes plus paper execution.

Responsibilities:
- consume ``engine:commands`` (submit/cancel orders, run lifecycle) from the
  Redis stream, with DB reconciliation at startup for missed commands;
- consume the ``md:ticks`` fan-in channel and drive paper fills plus strategy
  callbacks;
- maintain position marks, account equity, portfolio snapshots, run
  heartbeats, and the daily-loss guard.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import socket
from collections.abc import Awaitable
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.config import Settings, get_settings
from algo_platform.modules.billing.application.service import SubscriptionService
from algo_platform.modules.brokerage.infrastructure.models import TradingAccountModel
from algo_platform.modules.market_intel.application.client import AicioClient
from algo_platform.modules.market_intel.application.shadow_gate import ShadowGate
from algo_platform.modules.market_intel.infrastructure.duckdb_reader import get_aicio_reader
from algo_platform.modules.notifications.application.service import NotificationService
from algo_platform.modules.risk.application.service import RiskService
from algo_platform.modules.strategies.application.runtime import (
    StrategyRuntime,
    load_runtime,
)
from algo_platform.modules.strategies.application.service import apply_run, run_entity
from algo_platform.modules.strategies.domain.strategies import RunState
from algo_platform.modules.strategies.infrastructure.artifact_store import ArtifactStore
from algo_platform.modules.strategies.infrastructure.models import StrategyRunModel
from algo_platform.modules.trading.application.execution_engine import (
    PaperExecutionEngine,
)
from algo_platform.modules.trading.application.live_router import LiveRouter
from algo_platform.modules.trading.application.order_service import daily_pnl_key
from algo_platform.modules.trading.infrastructure.brokers.paper import (
    PaperExecutionSimulator,
)
from algo_platform.shared.domain.types import AccountId, TenantId, utc_now
from algo_platform.shared.infrastructure.database import (
    create_engine,
    create_session_factory,
)
from algo_platform.shared.infrastructure.encryption import CredentialCipher
from algo_platform.shared.infrastructure.metrics_server import start_process_metrics
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway
from algo_platform.shared.infrastructure.secrets import (
    SecretsResolver,
    build_secrets_provider,
)
from algo_platform.shared.infrastructure.telemetry import configure_logging

logger = structlog.get_logger("trading_engine")

COMMAND_STREAM = "engine:commands"
COMMAND_GROUP = "trading-engine-v1"
HEARTBEAT_KEY = "hb:trading_engine"
MARKS_INTERVAL_SECONDS = 5.0
SNAPSHOT_INTERVAL_SECONDS = 60.0
RUN_HEARTBEAT_INTERVAL_SECONDS = 20.0


class TradingEngineProcess:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        secrets = SecretsResolver(build_secrets_provider(settings), settings)
        self._db_engine = create_engine(settings.database_url, pool_size=8)
        self._session_factory = create_session_factory(self._db_engine)
        self._redis = RedisGateway.from_url(settings.redis_url)
        self._paper = PaperExecutionEngine(
            session_factory=self._session_factory,
            redis=self._redis,
            simulator=PaperExecutionSimulator(seed=settings.market_data_seed),
        )
        self._artifacts = ArtifactStore(settings.strategy_artifact_dir)
        self._live = LiveRouter(
            session_factory=self._session_factory,
            redis=self._redis,
            cipher=CredentialCipher.from_base64(
                secrets.broker_credential_kek_b64(),
                key_version=settings.credential_key_version,
            ),
            mt5_allowed_hosts=settings.mt5_agent_allowed_hosts,
            mt5_require_https=settings.app_env not in {"local", "test"},
        )
        self._runtimes: dict[UUID, StrategyRuntime] = {}
        self._loss_guard_tripped: set[str] = set()
        self._stop = asyncio.Event()
        self._consumer_name = f"{socket.gethostname()}-{os.getpid()}"
        self._metrics = start_process_metrics(settings, "algo-trading-engine")
        # Advisory market-intelligence gate. When AI-CIO is configured it logs,
        # at each run start, what it *would* advise — it never changes execution.
        self._shadow_gate: ShadowGate | None = None
        if settings.aicio_shadow_gate_enabled and settings.aicio_duckdb_path is not None:
            self._shadow_gate = ShadowGate(
                AicioClient(get_aicio_reader(settings.aicio_duckdb_path))
            )

    def _billing_factory(self, session: AsyncSession) -> SubscriptionService:
        return SubscriptionService(
            session=session,
            providers={},
            app_base_url=self._settings.app_base_url,
            notifications=NotificationService(session, self._redis),
        )

    # -- lifecycle ----------------------------------------------------------------

    async def run(self) -> None:
        _install_signal_handlers(self._stop)
        await self._paper.recover()
        await self._recover_runs()
        tasks = [
            asyncio.create_task(self._consume_commands(), name="commands"),
            asyncio.create_task(self._consume_ticks(), name="ticks"),
            asyncio.create_task(self._periodic_maintenance(), name="maintenance"),
        ]
        logger.info("engine.started", runtimes=len(self._runtimes))
        await self._stop.wait()
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._shutdown_runtimes()
        await self._live.shutdown()
        await self._redis.close()
        await self._db_engine.dispose()
        logger.info("engine.stopped")

    async def _recover_runs(self) -> None:
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(StrategyRunModel).where(
                            StrategyRunModel.state.in_(
                                ["starting", "running", "paused", "stopping"]
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
            for model in rows:
                if model.state == "stopping":
                    run = run_entity(model)
                    run.mark_stopped()
                    apply_run(model, run)
                    continue
                try:
                    runtime = await load_runtime(
                        run_model=model,
                        session=session,
                        session_factory=self._session_factory,
                        redis=self._redis,
                        billing_factory=self._billing_factory,
                        artifacts=self._artifacts,
                    )
                except LookupError as error:
                    run = run_entity(model)
                    run.mark_failed(str(error))
                    apply_run(model, run)
                    continue
                if model.state == "starting":
                    await runtime.start()
                    runtime.run.mark_running()
                elif model.state == "running":
                    runtime.run.state = RunState.RUNNING
                elif model.state == "paused":
                    runtime.run.state = RunState.PAUSED
                apply_run(model, runtime.run)
                self._runtimes[runtime.run_id] = runtime
            await session.commit()
        for runtime in self._runtimes.values():
            if runtime.run.state is RunState.RUNNING:
                await self._shadow_evaluate(runtime)

    async def _shutdown_runtimes(self) -> None:
        for runtime in list(self._runtimes.values()):
            await runtime.shutdown()
            await self._persist_run(runtime)

    # -- command stream --------------------------------------------------------------

    async def _consume_commands(self) -> None:
        await self._ensure_command_group()
        while not self._stop.is_set():
            try:
                claimed = await cast(
                    Awaitable[Any],
                    self._redis.raw.xautoclaim(
                        COMMAND_STREAM,
                        COMMAND_GROUP,
                        self._consumer_name,
                        min_idle_time=30_000,
                        start_id="0-0",
                        count=50,
                    ),
                )
                claimed_entries = claimed[1] if claimed and len(claimed) > 1 else []
                if claimed_entries:
                    await self._handle_command_entries(claimed_entries)
                    continue
                response = await cast(
                    Awaitable[Any],
                    self._redis.raw.xreadgroup(
                        COMMAND_GROUP,
                        self._consumer_name,
                        {COMMAND_STREAM: ">"},
                        block=2000,
                        count=50,
                    ),
                )
            except Exception as error:
                logger.warning("engine.command_read_failed", error=type(error).__name__)
                await asyncio.sleep(2)
                continue
            if not response:
                continue
            for _stream, entries in response:
                await self._handle_command_entries(entries)

    async def _ensure_command_group(self) -> None:
        try:
            await cast(
                Awaitable[Any],
                self._redis.raw.xgroup_create(
                    COMMAND_STREAM,
                    COMMAND_GROUP,
                    id="0-0",
                    mkstream=True,
                ),
            )
        except Exception as error:
            if "BUSYGROUP" not in str(error):
                raise

    async def _handle_command_entries(self, entries: list[Any]) -> None:
        for entry_id, fields in entries:
            payload = _decode_command(fields)
            if payload is None:
                logger.error("engine.command_malformed", stream_id=entry_id)
                await cast(
                    Awaitable[Any],
                    self._redis.raw.xack(COMMAND_STREAM, COMMAND_GROUP, entry_id),
                )
                continue
            if await self._dispatch_command(payload):
                await cast(
                    Awaitable[Any],
                    self._redis.raw.xack(COMMAND_STREAM, COMMAND_GROUP, entry_id),
                )

    async def _dispatch_command(self, command: dict[str, Any]) -> bool:
        kind = str(command.get("type", ""))
        try:
            if kind == "submit_order":
                order_id = UUID(str(command["order_id"]))
                if command.get("mode") == "live":
                    await self._live.submit(order_id)
                else:
                    await self._paper.handle_submit(order_id)
            elif kind == "cancel_order":
                order_id = UUID(str(command["order_id"]))
                mode = await self._account_mode_for_order(order_id)
                if mode == "live":
                    await self._live.cancel(order_id)
                else:
                    await self._paper.handle_cancel(order_id)
            elif kind in {"start_run", "resume_run"}:
                await self._start_run(UUID(str(command["run_id"])))
            elif kind == "pause_run":
                await self._pause_run(UUID(str(command["run_id"])))
            elif kind == "stop_run":
                await self._stop_run(UUID(str(command["run_id"])))
            else:
                logger.warning("engine.unknown_command", kind=kind)
                return True
        except Exception:
            logger.exception("engine.command_failed", kind=kind)
            return False
        return True

    async def _account_mode_for_order(self, order_id: UUID) -> str:
        from algo_platform.modules.trading.infrastructure.models import OrderModel

        async with self._session_factory() as session:
            order_model = await session.get(OrderModel, order_id)
            if order_model is None:
                return "paper"
            account = await session.get(TradingAccountModel, order_model.account_id)
            return account.mode if account is not None else "paper"

    async def _start_run(self, run_id: UUID) -> None:
        if run_id in self._runtimes:
            runtime = self._runtimes[run_id]
            if runtime.run.state is RunState.PAUSED:
                runtime.run.mark_running()
                await self._persist_run(runtime)
            return
        async with self._session_factory() as session:
            model = await session.get(StrategyRunModel, run_id)
            if model is None or model.state not in {"starting", "pending"}:
                return
            try:
                runtime = await load_runtime(
                    run_model=model,
                    session=session,
                    session_factory=self._session_factory,
                    redis=self._redis,
                    billing_factory=self._billing_factory,
                    artifacts=self._artifacts,
                )
            except LookupError as error:
                run = run_entity(model)
                run.mark_failed(str(error))
                apply_run(model, run)
                await session.commit()
                return
            await session.commit()
        await runtime.start()
        if runtime.failed_reason:
            runtime.run.mark_failed(runtime.failed_reason)
        else:
            runtime.run.mark_running()
            self._runtimes[runtime.run_id] = runtime
        await self._persist_run(runtime)
        if not runtime.failed_reason:
            await self._shadow_evaluate(runtime)
        logger.info("engine.run_started", run_id=str(run_id), state=runtime.run.state.value)

    async def _pause_run(self, run_id: UUID) -> None:
        runtime = self._runtimes.get(run_id)
        if runtime is None:
            return
        if runtime.run.state is RunState.RUNNING:
            runtime.run.pause()
        await self._persist_run(runtime)

    async def _stop_run(self, run_id: UUID) -> None:
        runtime = self._runtimes.pop(run_id, None)
        if runtime is None:
            async with self._session_factory() as session:
                model = await session.get(StrategyRunModel, run_id)
                if model is not None and model.state in {"stopping", "starting", "pending"}:
                    run = run_entity(model)
                    run.mark_stopped()
                    apply_run(model, run)
                    await session.commit()
            return
        await runtime.shutdown()
        runtime.run.mark_stopped()
        await self._persist_run(runtime)
        logger.info("engine.run_stopped", run_id=str(run_id))

    async def _persist_run(self, runtime: StrategyRuntime) -> None:
        async with self._session_factory() as session:
            model = await session.get(StrategyRunModel, runtime.run_id)
            if model is None:
                return
            runtime.run.heartbeat(runtime.stats())
            apply_run(model, runtime.run)
            await session.commit()
        await self._redis.publish_json(
            f"strategy-runs:{runtime.run.organization_id}",
            {
                "channel": "strategy-runs",
                "run_id": str(runtime.run_id),
                "state": runtime.run.state.value,
                "error": runtime.run.error,
                "stats": runtime.stats(),
            },
        )

    async def _shadow_evaluate(self, runtime: StrategyRuntime) -> None:
        """Log the advisory market-intel opinion for a run start. Never affects
        execution; a no-op unless the AI-CIO shadow gate is configured."""
        if self._shadow_gate is None:
            return
        await self._shadow_gate.evaluate(
            run_id=str(runtime.run_id),
            entry_point=runtime.entry_point,
            source=runtime.source,
            symbols=runtime.instrument_symbols,
        )

    # -- market data --------------------------------------------------------------------

    async def _consume_ticks(self) -> None:
        while not self._stop.is_set():
            try:
                async for _channel, tick in self._redis.subscribe_json("md:ticks"):
                    if self._metrics is not None:
                        self._metrics.market_ticks_total.labels(
                            source=self._settings.market_data_source
                        ).inc()
                        with self._metrics.engine_tick_duration_seconds.time():
                            await self._on_tick(tick)
                    else:
                        await self._on_tick(tick)
                    if self._stop.is_set():
                        break
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("engine.tick_stream_failed", error=type(error).__name__)
                await asyncio.sleep(2)

    async def _on_tick(self, tick: dict[str, Any]) -> None:
        try:
            instrument_id = UUID(str(tick["instrument_id"]))
            bid = Decimal(str(tick["bid"]))
            ask = Decimal(str(tick["ask"]))
            last = Decimal(str(tick["last"]))
        except (KeyError, ValueError, ArithmeticError):
            return
        touched = await self._paper.on_tick(instrument_id, bid, ask)
        for account_id in touched:
            await self._check_daily_loss_guard(account_id)
        failed: list[UUID] = []
        for runtime in self._runtimes.values():
            if instrument_id in runtime.instrument_ids:
                await runtime.on_tick(instrument_id, bid=bid, ask=ask, last=last)
                if runtime.failed_reason:
                    failed.append(runtime.run_id)
        for run_id in failed:
            runtime = self._runtimes.pop(run_id)
            runtime.run.mark_failed(runtime.failed_reason or "strategy failure")
            await self._persist_run(runtime)

    async def _check_daily_loss_guard(self, account_id: UUID) -> None:
        guard_key = f"{account_id}:{utc_now():%Y%m%d}"
        if guard_key in self._loss_guard_tripped:
            return
        raw = await self._redis.get_str(daily_pnl_key(AccountId(account_id)))
        if raw is None:
            return
        try:
            realized_today = Decimal(raw)
        except ArithmeticError:
            return
        async with self._session_factory() as session:
            account = await session.get(TradingAccountModel, account_id)
            if account is None:
                return
            risk = RiskService(session)
            limits = await risk.get_effective_limits(
                TenantId(account.organization_id), AccountId(account_id)
            )
            if realized_today > -limits.max_daily_loss:
                await session.commit()
                return
            self._loss_guard_tripped.add(guard_key)
            await risk.record_event(
                TenantId(account.organization_id),
                account_id=AccountId(account_id),
                event_type="max_daily_loss_breached",
                severity="critical",
                message=(
                    f"daily realized loss {realized_today} breached the limit "
                    f"{limits.max_daily_loss}; pausing strategy runs on the account"
                ),
                details={"realized_today": str(realized_today)},
            )
            await NotificationService(session, self._redis).notify(
                organization_id=account.organization_id,
                title="Daily loss limit breached",
                body="Strategy runs on the affected account were paused.",
                type_="risk",
                severity="critical",
            )
            await session.commit()
        for runtime in self._runtimes.values():
            if runtime.run.account_id == account_id and (runtime.run.state is RunState.RUNNING):
                runtime.run.pause()
                await self._persist_run(runtime)

    # -- maintenance -----------------------------------------------------------------------

    async def _periodic_maintenance(self) -> None:
        last_snapshot = 0.0
        last_heartbeat = 0.0
        loop = asyncio.get_event_loop()
        while not self._stop.is_set():
            now = loop.time()
            try:
                prices = await self._redis.hgetall_json("md:last")
                await self._paper.refresh_marks_and_equity(prices)
                if now - last_snapshot >= SNAPSHOT_INTERVAL_SECONDS:
                    await self._paper.write_snapshots()
                    last_snapshot = now
                if now - last_heartbeat >= RUN_HEARTBEAT_INTERVAL_SECONDS:
                    for runtime in list(self._runtimes.values()):
                        await self._persist_run(runtime)
                    last_heartbeat = now
                await self._redis.set_str(HEARTBEAT_KEY, utc_now().isoformat(), ttl_seconds=120)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("engine.maintenance_failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=MARKS_INTERVAL_SECONDS)


def _decode_command(fields: dict[Any, Any]) -> dict[str, Any] | None:
    import json

    raw = fields.get("payload") or fields.get(b"payload")
    if raw is None:
        return None
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        loaded = json.loads(text)
        return cast(dict[str, Any], loaded)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_event_loop()
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())


async def run() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, env=settings.app_env, service="algo-trading-engine")
    process = TradingEngineProcess(settings)
    await process.run()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
