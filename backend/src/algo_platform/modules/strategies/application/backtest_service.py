"""Backtest application service: run, persist, and query backtests."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.strategies.application.backtest_signals import build_signal
from algo_platform.modules.strategies.domain.backtest import (
    BacktestConfig,
    BacktestResult,
    Bar,
    MonteCarloResult,
    grid_search,
    monte_carlo,
    run_backtest,
)
from algo_platform.modules.strategies.infrastructure.models import BacktestRunModel
from algo_platform.shared.domain.errors import NotFoundError, ValidationFailed
from algo_platform.shared.domain.types import TenantId, utc_now

_MAX_BARS = 20_000


class BacktestService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _bars(self, raw: list[dict[str, float]]) -> list[Bar]:
        if not 2 <= len(raw) <= _MAX_BARS:
            raise ValidationFailed(f"a backtest needs 2..{_MAX_BARS} bars")
        return [
            Bar(
                open=float(b["open"]),
                high=float(b["high"]),
                low=float(b["low"]),
                close=float(b["close"]),
                volume=float(b.get("volume", 0.0)),
            )
            for b in raw
        ]

    async def run(
        self,
        organization_id: TenantId,
        *,
        signal_type: str,
        params: dict[str, float],
        bars: list[dict[str, float]],
        config: BacktestConfig | None = None,
    ) -> tuple[UUID, BacktestResult]:
        signal = build_signal(signal_type, params)
        cfg = config or BacktestConfig()
        result = run_backtest(self._bars(bars), signal, cfg)
        run_id = uuid4()
        self._session.add(
            BacktestRunModel(
                id=run_id,
                organization_id=organization_id,
                signal_type=signal_type,
                params=dict(params),
                config=asdict(cfg),
                result=_result_summary(result),
                created_at=utc_now(),
            )
        )
        await self._session.flush()
        return run_id, result

    def monte_carlo(
        self, result: BacktestResult, *, iterations: int, seed: int
    ) -> MonteCarloResult:
        return monte_carlo(result.returns, iterations=iterations, seed=seed)

    def optimize(
        self,
        *,
        signal_type: str,
        grid: dict[str, list[float]],
        bars: list[dict[str, float]],
        objective: str = "sharpe",
        config: BacktestConfig | None = None,
    ) -> list[dict[str, object]]:
        selector = {
            "sharpe": lambda r: r.sharpe,
            "total_return": lambda r: r.total_return_pct,
            "calmar": lambda r: r.calmar,
        }.get(objective)
        if selector is None:
            raise ValidationFailed(f"unknown objective '{objective}'")
        ranked = grid_search(
            self._bars(bars),
            grid,
            lambda p: build_signal(signal_type, p),
            objective=selector,
            config=config,
        )
        return [
            {"params": opt.params, "score": round(opt.score, 4), **_result_summary(opt.result)}
            for opt in ranked[:20]
        ]

    async def list_runs(
        self, organization_id: TenantId, *, limit: int, offset: int
    ) -> list[dict[str, object]]:
        rows = (
            await self._session.execute(
                select(BacktestRunModel)
                .where(BacktestRunModel.organization_id == organization_id)
                .order_by(BacktestRunModel.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        return [_run_to_dict(r) for r in rows]

    async def get_run(self, organization_id: TenantId, run_id: UUID) -> dict[str, object]:
        model = await self._session.get(BacktestRunModel, run_id)
        if model is None or model.organization_id != organization_id:
            raise NotFoundError("backtest run not found")
        return _run_to_dict(model)


def _result_summary(result: BacktestResult) -> dict[str, object]:
    data = asdict(result)
    # The full equity curve/returns can be large; keep the scored summary.
    data.pop("equity_curve", None)
    data.pop("returns", None)
    return data


def _run_to_dict(model: BacktestRunModel) -> dict[str, object]:
    created: datetime = model.created_at
    return {
        "id": str(model.id),
        "signal_type": model.signal_type,
        "params": model.params,
        "config": model.config,
        "result": model.result,
        "created_at": created.isoformat(),
    }
