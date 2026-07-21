"""Unit tests for the regime→strategy-family favourability rule and the
entry-point / type → family mappings that drive the advisory shadow gate.

Pure logic: no database, no engine, no I/O.
"""

from __future__ import annotations

import pytest

from algo_platform.modules.market_intel.application.client import family_from_type
from algo_platform.modules.market_intel.application.shadow_gate import family_for
from algo_platform.modules.market_intel.domain.indices import INDEX_GROUPS, symbols_for_index
from algo_platform.modules.market_intel.domain.regime import StrategyFamily, is_favourable


def test_symbols_for_index_known_and_case_insensitive() -> None:
    assert "HDFCBANK" in (symbols_for_index("banknifty") or frozenset())
    assert "RELIANCE" in (symbols_for_index("nifty50") or frozenset())
    assert symbols_for_index("BankNifty") is not None  # case-insensitive
    assert symbols_for_index("nonsense") is None


def test_every_index_group_resolves() -> None:
    for value, label in INDEX_GROUPS:
        assert label
        assert symbols_for_index(value), f"{value} has no constituents"


_SMA = "algo_platform.modules.strategies.builtin.sma_crossover:SmaCrossover"
_RSI = "algo_platform.modules.strategies.builtin.rsi_reversion:RsiReversion"
_MOM = "algo_platform.modules.strategies.builtin.momentum_breakout:MomentumBreakout"


@pytest.mark.parametrize(
    ("regime", "family", "expected"),
    [
        ("trending_low", StrategyFamily.MOMENTUM, True),
        ("trending_high", StrategyFamily.MOMENTUM, True),
        ("trending_normal", StrategyFamily.MEAN_REVERSION, False),
        ("ranging_low", StrategyFamily.MEAN_REVERSION, True),
        ("ranging_normal", StrategyFamily.MEAN_REVERSION, True),
        ("ranging_low", StrategyFamily.MOMENTUM, False),
        ("ranging_high", StrategyFamily.MEAN_REVERSION, False),
        ("ranging_high", StrategyFamily.MOMENTUM, False),
        ("risk_on", StrategyFamily.MOMENTUM, True),
        ("risk_off", StrategyFamily.MOMENTUM, False),
        ("risk_off", StrategyFamily.MEAN_REVERSION, False),
        ("recovery_transition", StrategyFamily.MOMENTUM, False),
    ],
)
def test_is_favourable_table(regime: str, family: StrategyFamily, expected: bool) -> None:
    assert is_favourable(regime, family) is expected


def test_unknown_family_is_fail_open() -> None:
    # The gate holds no opinion on strategies it cannot classify.
    for regime in ("trending_low", "risk_off", "ranging_high"):
        assert is_favourable(regime, StrategyFamily.UNKNOWN) is True


def test_unknown_regime_is_fail_open() -> None:
    # A label added upstream later must not silently discourage anything.
    assert is_favourable("some_future_regime", StrategyFamily.MOMENTUM) is True
    assert is_favourable("some_future_regime", StrategyFamily.MEAN_REVERSION) is True


@pytest.mark.parametrize(
    ("entry_point", "source", "expected"),
    [
        (_SMA, "builtin", StrategyFamily.MOMENTUM),
        (_RSI, "builtin", StrategyFamily.MEAN_REVERSION),
        (_MOM, "builtin", StrategyFamily.MOMENTUM),
        ("user_module:Whatever", "upload", StrategyFamily.UNKNOWN),
        # A builtin-looking path from a non-builtin source stays UNKNOWN.
        (_SMA, "upload", StrategyFamily.UNKNOWN),
    ],
)
def test_family_for(entry_point: str, source: str, expected: StrategyFamily) -> None:
    assert family_for(entry_point, source) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("momentum", StrategyFamily.MOMENTUM),
        ("mean_reversion", StrategyFamily.MEAN_REVERSION),
        ("MEAN_REVERSION", StrategyFamily.MEAN_REVERSION),
        ("nonsense", StrategyFamily.UNKNOWN),
    ],
)
def test_family_from_type(value: str, expected: StrategyFamily) -> None:
    assert family_from_type(value) is expected
