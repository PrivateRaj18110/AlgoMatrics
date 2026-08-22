"""Canonical trade vs non-trade kinds for the /app read layer.

Must stay equal to ``ops/backend/app/services/telemetry_classification.py``
(commit ``f9bee1a``). Ingest still classifies; this module only documents the
contract so the main API never reinterprets heartbeats as trades.
"""

from __future__ import annotations

TRADE_KINDS = frozenset({"trade", "trade_closed"})

NON_TRADE_KINDS = frozenset(
    {
        "heartbeat",
        "metrics",
        "metric",
        "event",
        "error",
        "position",
        "start",
        "stop",
        "log",
        "system_status",
        "strategy_status",
        "signal",
        "order",
        "fill",
        "pnl",
        "risk",
        "sync_status",
        "recovery",
    }
)
