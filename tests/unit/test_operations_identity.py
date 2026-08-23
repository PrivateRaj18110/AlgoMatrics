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
    assert strategy_identity("Alpha", None) == "Alpha"


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


def test_demo_rows_are_identifiable() -> None:
    from algo_platform.modules.operations.application.suspect import (
        is_demo_blotter_row,
        is_demo_machine,
    )

    demo_trade = {
        "id": "trd-demo-1",
        "envelope_id": None,
        "strategy": "Mean Reversion FX",
        "machine": "London VPS",
        "machine_id": "mch-london",
    }
    assert is_demo_blotter_row(demo_trade) is True

    real_trade = {
        "id": "trd-1",
        "envelope_id": "env-1",
        "strategy": "Alpha",
        "machine": "gcp-trading-1",
        "machine_id": "mch-agent-gcp-1",
    }
    assert is_demo_blotter_row(real_trade) is False

    # A real trade where envelope_id is None must NOT be flagged as demo
    real_trade_no_envelope = {
        "id": "trd-2",
        "envelope_id": None,
        "strategy": "Alpha",
        "machine": "gcp-trading-1",
        "machine_id": "mch-agent-gcp-1",
        "broker": "Zerodha",
        "account": "ACC-1234",
    }
    assert is_demo_blotter_row(real_trade_no_envelope) is False

    demo_machine = {"id": "mch-london", "name": "London VPS", "live": 0}
    assert is_demo_machine(demo_machine) is True

    real_machine = {"id": "mch-agent-gcp-1", "name": "gcp-trading-1", "live": 1}
    assert is_demo_machine(real_machine) is False


