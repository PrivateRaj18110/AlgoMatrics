"""Unit tests for backtest signal builders (Phase 12, slice B)."""

from __future__ import annotations

import pytest

from algo_platform.modules.strategies.application.backtest_signals import (
    available_signal_types,
    build_signal,
)
from algo_platform.modules.strategies.domain.backtest import Bar
from algo_platform.shared.domain.errors import ValidationFailed


def _bars(prices: list[float]) -> list[Bar]:
    return [Bar(open=p, high=p, low=p, close=p) for p in prices]


def test_available_signal_types() -> None:
    assert set(available_signal_types()) == {"sma_crossover", "rsi_reversion", "breakout"}


def test_unknown_type_rejected() -> None:
    with pytest.raises(ValidationFailed):
        build_signal("nope", {})


def test_sma_crossover_validates_params() -> None:
    with pytest.raises(ValidationFailed):
        build_signal("sma_crossover", {"fast": 30, "slow": 10})


def test_sma_crossover_goes_long_when_fast_above_slow() -> None:
    signal = build_signal("sma_crossover", {"fast": 2, "slow": 4})
    # Rising series -> fast MA above slow MA -> long.
    assert signal(_bars([100, 101, 102, 103, 104, 105])) == 1
    # Not enough history -> flat.
    assert signal(_bars([100, 101])) == 0


def test_breakout_triggers_above_prior_high() -> None:
    signal = build_signal("breakout", {"lookback": 3})
    assert signal([Bar(open=1, high=h, low=1, close=h) for h in [10, 11, 12, 13, 20]]) == 1
    assert signal([Bar(open=1, high=h, low=1, close=1) for h in [10, 11, 12, 13, 12]]) == 0


def test_rsi_reversion_exits_when_overbought() -> None:
    signal = build_signal("rsi_reversion", {"period": 3, "oversold": 30, "overbought": 70})
    # Straight up -> RSI ~100 -> flat (exit).
    assert signal(_bars([100, 101, 102, 103, 104])) == 0
