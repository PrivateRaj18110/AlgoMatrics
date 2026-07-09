"""Bar-based signal builders for backtesting the built-in strategy types.

These mirror the built-in strategies' candle logic as pure functions over a bar
window, so the backtest engine can run them without the async SDK runtime. New
strategy types register here to become backtestable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from algo_platform.modules.strategies.domain.backtest import Bar, SignalFn
from algo_platform.shared.domain.errors import ValidationFailed


def _sma(closes: Sequence[float], window: int) -> float:
    return sum(closes[-window:]) / window


def build_sma_crossover(params: Mapping[str, float]) -> SignalFn:
    fast = int(params.get("fast", 10))
    slow = int(params.get("slow", 30))
    if fast < 1 or slow <= fast:
        raise ValidationFailed("sma_crossover requires 1 <= fast < slow")

    def signal(history: Sequence[Bar]) -> int:
        if len(history) < slow:
            return 0
        closes = [b.close for b in history]
        return 1 if _sma(closes, fast) > _sma(closes, slow) else 0

    return signal


def build_rsi_reversion(params: Mapping[str, float]) -> SignalFn:
    period = int(params.get("period", 14))
    oversold = float(params.get("oversold", 30))
    overbought = float(params.get("overbought", 70))
    if period < 2 or not 0 < oversold < overbought < 100:
        raise ValidationFailed("invalid rsi_reversion parameters")

    def signal(history: Sequence[Bar]) -> int:
        if len(history) <= period:
            return 0
        closes = [b.close for b in history[-(period + 1) :]]
        gains = sum(max(0.0, closes[i] - closes[i - 1]) for i in range(1, len(closes)))
        losses = sum(max(0.0, closes[i - 1] - closes[i]) for i in range(1, len(closes)))
        if losses == 0:
            rsi = 100.0
        else:
            rs = (gains / period) / (losses / period)
            rsi = 100.0 - 100.0 / (1.0 + rs)
        # Mean reversion: hold a long only while the market is below the
        # overbought line, entering with conviction under oversold.
        return 1 if rsi < overbought else 0

    return signal


def build_breakout(params: Mapping[str, float]) -> SignalFn:
    lookback = int(params.get("lookback", 20))
    if lookback < 2:
        raise ValidationFailed("breakout requires lookback >= 2")

    def signal(history: Sequence[Bar]) -> int:
        if len(history) <= lookback:
            return 0
        window = history[-(lookback + 1) : -1]
        high = max(b.high for b in window)
        return 1 if history[-1].close > high else 0

    return signal


_BUILDERS = {
    "sma_crossover": build_sma_crossover,
    "rsi_reversion": build_rsi_reversion,
    "breakout": build_breakout,
}


def available_signal_types() -> list[str]:
    return sorted(_BUILDERS)


def build_signal(signal_type: str, params: Mapping[str, float]) -> SignalFn:
    builder = _BUILDERS.get(signal_type)
    if builder is None:
        raise ValidationFailed(f"unknown strategy type '{signal_type}'")
    return builder(params)
