"""Unit tests for the market-intel shadow gate.

The gate is advisory and **log-only**: it emits what AI-CIO *would* advise for a
run start and must never raise or change anything. These tests capture its log
output and assert the opinions are right, that missing data is a no-op, and that
a failing client is swallowed (a broken advisory path must not break run startup).
"""

from __future__ import annotations

from typing import Any

from structlog.testing import capture_logs

from algo_platform.modules.market_intel.application.shadow_gate import ShadowGate
from algo_platform.modules.market_intel.domain.regime import RankingRow, Regime

_SMA = "algo_platform.modules.strategies.builtin.sma_crossover:SmaCrossover"  # momentum


def _regime(label: str) -> Regime:
    return Regime(
        label=label,
        hmm_confidence=0.8,
        hmm_vol_state="low",
        gmm_vol_state="low",
        adx_14=20.0,
        avg_pairwise_corr=0.2,
        breadth_pct_above_ma20=0.5,
        days_since_changepoint=10,
        as_of="2026-07-16",
    )


def _ranking(ticker: str, rank: int) -> RankingRow:
    return RankingRow(
        run_date="2026-07-16",
        ticker=ticker,
        name=ticker,
        rank=rank,
        composite_score=1.0,
        regime="ranging_low",
        dimensions=(),
    )


class _FakeClient:
    """Duck-typed stand-in for AicioClient recording that only reads happen."""

    def __init__(
        self,
        regime: Regime | None,
        rankings: list[RankingRow] | None = None,
        *,
        raise_on_regime: bool = False,
    ) -> None:
        self._regime = regime
        self._rankings = rankings or []
        self._raise_on_regime = raise_on_regime
        self.calls: list[str] = []

    async def current_regime(self) -> Regime | None:
        self.calls.append("current_regime")
        if self._raise_on_regime:
            raise RuntimeError("duckdb exploded")
        return self._regime

    async def rankings(self, top_n: int = 20, ticker: str | None = None) -> list[RankingRow]:
        self.calls.append("rankings")
        return self._rankings


def _event(logs: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((entry for entry in logs if entry.get("event") == name), None)


async def test_logs_would_suspend_for_unfavourable_regime() -> None:
    # A momentum strategy in a ranging_low regime is not favoured → would suspend.
    client = _FakeClient(_regime("ranging_low"), [_ranking("RELIANCE", 1)])
    gate = ShadowGate(client)  # type: ignore[arg-type]

    with capture_logs() as logs:
        await gate.evaluate(run_id="r1", entry_point=_SMA, source="builtin", symbols=["RELIANCE"])

    regime_opinion = _event(logs, "shadow_gate.regime_opinion")
    assert regime_opinion is not None
    assert regime_opinion["would_suspend"] is True
    assert regime_opinion["family"] == "momentum"
    assert regime_opinion["mode"] == "shadow"

    ranking_opinion = _event(logs, "shadow_gate.ranking_opinion")
    assert ranking_opinion is not None
    assert ranking_opinion["would_exclude"] == []  # RELIANCE is in the ranking


async def test_logs_would_exclude_unranked_symbol() -> None:
    # A momentum strategy in a favourable regime, but on a symbol that failed the
    # quality gate (absent from the ranking) → would exclude that symbol.
    client = _FakeClient(_regime("trending_low"), [_ranking("RELIANCE", 1)])
    gate = ShadowGate(client)  # type: ignore[arg-type]

    with capture_logs() as logs:
        await gate.evaluate(run_id="r2", entry_point=_SMA, source="builtin", symbols=["ZZZZ"])

    regime_opinion = _event(logs, "shadow_gate.regime_opinion")
    assert regime_opinion is not None and regime_opinion["would_suspend"] is False
    ranking_opinion = _event(logs, "shadow_gate.ranking_opinion")
    assert ranking_opinion is not None
    assert ranking_opinion["would_exclude"] == ["ZZZZ"]


async def test_no_data_is_a_noop() -> None:
    client = _FakeClient(regime=None)
    gate = ShadowGate(client)  # type: ignore[arg-type]

    with capture_logs() as logs:
        await gate.evaluate(run_id="r3", entry_point=_SMA, source="builtin", symbols=["RELIANCE"])

    assert _event(logs, "shadow_gate.no_data") is not None
    assert _event(logs, "shadow_gate.regime_opinion") is None
    assert "rankings" not in client.calls  # short-circuits before scanning rankings


async def test_client_failure_is_swallowed() -> None:
    # A broken advisory path must never break run startup.
    client = _FakeClient(_regime("ranging_low"), raise_on_regime=True)
    gate = ShadowGate(client)  # type: ignore[arg-type]

    with capture_logs() as logs:
        result = await gate.evaluate(
            run_id="r4", entry_point=_SMA, source="builtin", symbols=["RELIANCE"]
        )

    assert result is None
    assert _event(logs, "shadow_gate.evaluate_failed") is not None


async def test_gate_only_reads_never_writes() -> None:
    # Structural guarantee: the gate's client interaction is read-only.
    client = _FakeClient(_regime("trending_low"), [_ranking("RELIANCE", 1)])
    gate = ShadowGate(client)  # type: ignore[arg-type]

    await gate.evaluate(run_id="r5", entry_point=_SMA, source="builtin", symbols=["RELIANCE"])

    assert set(client.calls) <= {"current_regime", "rankings"}
