from algo_platform.modules.operations.application.analytics import (
    aggregate_strategies,
    aggregate_symbols,
)
from algo_platform.modules.operations.application.instrument import parse_instrument
from algo_platform.modules.operations.application.suspect import is_suspect_blotter_row
from algo_platform.modules.operations.domain.identity import strategy_identity


def test_strategy_identity_is_machine_plus_name() -> None:
    assert strategy_identity("Alpha", "mch-agent-gcp") == "mch-agent-gcp::Alpha"
    assert strategy_identity("Alpha", "mch-a") != strategy_identity("Alpha", "mch-b")
    assert strategy_identity("", "mch") == ""


def test_option_parts_only_when_present() -> None:
    parsed = parse_instrument("NIFTY 24500 CE")
    assert parsed.option_type == "CE"
    assert parsed.strike == "24500"
    assert parsed.metadata_available is True
    equity = parse_instrument("RELIANCE")
    assert equity.option_type is None
    assert equity.metadata_available is False


def test_suspect_rows_are_identifiable_without_delete() -> None:
    row = {
        "strategy": "unknown",
        "entry": 0,
        "exit": None,
        "pnl": 0,
        "duration_sec": 0,
        "status": "closed",
    }
    assert is_suspect_blotter_row(row) is True
    real = {**row, "strategy": "Alpha", "entry": 101.5, "pnl": 12.0}
    assert is_suspect_blotter_row(real) is False


def test_metrics_are_none_without_pnl() -> None:
    rows = aggregate_strategies(
        [{"strategy": "Alpha", "machine_id": "m1", "symbol": "NIFTY"}],
        [],
    )
    assert rows[0]["total_pnl"] is None
    assert rows[0]["win_rate"] is None


def test_symbols_stay_attached_to_strategy() -> None:
    trades = [
        {"strategy": "Alpha", "machine_id": "m1", "symbol": "NIFTY", "pnl": 10},
        {"strategy": "Beta", "machine_id": "m1", "symbol": "RELIANCE", "pnl": -4},
    ]
    alpha = aggregate_symbols(trades, "Alpha")
    assert [row["symbol"] for row in alpha] == ["NIFTY"]
