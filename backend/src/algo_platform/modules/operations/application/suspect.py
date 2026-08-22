"""Historical blotter rows that must not enter new analytics.

Approximately 1367 rows look like misclassified heartbeats (unknown strategy,
entry 0, no exit, pnl 0, duration 0, closed). They stay in the database.
"""

from __future__ import annotations

from typing import Any


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
