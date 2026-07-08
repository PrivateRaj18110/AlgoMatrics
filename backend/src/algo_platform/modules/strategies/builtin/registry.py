"""Registry of first-party, reviewed strategies allowed to run in-process."""

from __future__ import annotations

from typing import Any

from algo_strategy_sdk.strategy import Strategy

from algo_platform.modules.strategies.builtin.momentum_breakout import (
    MANIFEST as MOMENTUM_MANIFEST,
)
from algo_platform.modules.strategies.builtin.momentum_breakout import MomentumBreakout
from algo_platform.modules.strategies.builtin.rsi_reversion import (
    MANIFEST as RSI_MANIFEST,
)
from algo_platform.modules.strategies.builtin.rsi_reversion import RsiReversion
from algo_platform.modules.strategies.builtin.sma_crossover import (
    MANIFEST as SMA_MANIFEST,
)
from algo_platform.modules.strategies.builtin.sma_crossover import SmaCrossover

BUILTIN_MANIFESTS: dict[str, dict[str, Any]] = {
    str(SMA_MANIFEST["entry_point"]): SMA_MANIFEST,
    str(RSI_MANIFEST["entry_point"]): RSI_MANIFEST,
    str(MOMENTUM_MANIFEST["entry_point"]): MOMENTUM_MANIFEST,
}

_BUILTIN_CLASSES: dict[str, type[Strategy]] = {
    str(SMA_MANIFEST["entry_point"]): SmaCrossover,
    str(RSI_MANIFEST["entry_point"]): RsiReversion,
    str(MOMENTUM_MANIFEST["entry_point"]): MomentumBreakout,
}


def is_builtin(entry_point: str) -> bool:
    return entry_point in _BUILTIN_CLASSES


def create_builtin(entry_point: str) -> Strategy:
    try:
        return _BUILTIN_CLASSES[entry_point]()
    except KeyError as error:
        raise LookupError(f"unknown builtin strategy: {entry_point}") from error
