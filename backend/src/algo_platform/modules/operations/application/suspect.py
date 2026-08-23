"""Historical blotter rows that must not enter new analytics.

Approximately 1367 rows look like misclassified heartbeats (unknown strategy,
entry 0, no exit, pnl 0, duration 0, closed). They stay in the database.
"""

from __future__ import annotations

from typing import Any

DEMO_MACHINE_IDS = frozenset({"mch-london", "mch-gcloud", "mch-pc"})
DEMO_MACHINE_NAMES = frozenset({"london vps", "personal computer"})
DEMO_STRATEGY_NAMES = frozenset(
    {
        "mean reversion fx",
        "momentum breakout",
        "gold scalper",
        "stat arb pairs",
        "crypto trend",
        "index overnight",
        "news fade",
        "grid hedge",
        "vol harvest",
    }
)
DEMO_BROKER_NAMES = frozenset({"ic markets", "pepperstone", "interactive brokers", "binance"})
DEMO_ACCOUNT_NAMES = frozenset({"live-001", "live-002", "live-003", "prop-114", "demo-001"})


def is_suspect_blotter_row(trade: dict[str, Any]) -> bool:
    strategy = str(trade.get("strategy") or "").strip().lower()
    entry = trade.get("entry")
    exit_px = trade.get("exit")
    pnl = trade.get("pnl")
    duration = trade.get("duration_sec", trade.get("durationSec", 0))
    status = str(trade.get("status") or "").lower()
    return (
        strategy in {"", "unknown"}
        and (entry == 0 or entry == 0.0)
        and exit_px in (None, "")
        and (pnl == 0 or pnl == 0.0)
        and (duration == 0 or duration == 0.0)
        and status == "closed"
    )


def is_demo_blotter_row(trade: dict[str, Any]) -> bool:
    """Historical demo trades from the initial seed/mock catalogs.

    Identified strictly by confirmed demo machine/host identities or
    demo broker-account fixture pairs. Does not assume missing envelope_id = demo.
    """
    machine_id = str(trade.get("machine_id") or "").strip().lower()
    if machine_id in DEMO_MACHINE_IDS:
        return True
    machine = str(trade.get("machine") or "").strip().lower()
    if machine in DEMO_MACHINE_NAMES:
        return True
    broker = str(trade.get("broker") or "").strip().lower()
    account = str(trade.get("account") or "").strip().lower()
    return bool(broker in DEMO_BROKER_NAMES and account in DEMO_ACCOUNT_NAMES)


def is_demo_machine(machine: dict[str, Any]) -> bool:
    """Historical demo machine row (London VPS / personal computer / mock gcloud)."""
    mid = str(machine.get("id") or "").strip().lower()
    if mid in DEMO_MACHINE_IDS:
        return True
    name = str(machine.get("name") or "").strip().lower()
    if name in DEMO_MACHINE_NAMES:
        return True
    live = machine.get("live")
    return bool(live is False or live == 0)


