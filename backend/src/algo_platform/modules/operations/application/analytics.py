"""Strategy / symbol analytics from real closed trades only."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from algo_platform.modules.operations.application.instrument import parse_instrument
from algo_platform.modules.operations.domain.identity import strategy_identity


def _ratio(wins: int, losses: int) -> float | None:
    if wins + losses == 0:
        return None
    return wins / (wins + losses)


def aggregate_strategies(
    trades: list[dict[str, Any]],
    status_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}

    for event in status_events:
        name = event.get("strategy")
        sid = strategy_identity(name, event.get("machine_id"))
        if not sid:
            continue
        row = buckets.setdefault(
            sid,
            {
                "strategy_id": sid,
                "strategy_name": name,
                "machine_id": event.get("machine_id"),
                "status": "unknown",
                "last_heartbeat": event.get("time"),
                "symbols": [],
            },
        )
        row["last_heartbeat"] = event.get("time") or row.get("last_heartbeat")
        summary = str(event.get("payload_summary") or "").lower()
        if "running" in summary or "online" in summary:
            row["status"] = "online"
        elif "stop" in summary or "offline" in summary:
            row["status"] = "offline"

    for trade in trades:
        name = trade.get("strategy")
        sid = strategy_identity(name, trade.get("machine_id"))
        if not sid:
            continue
        row = buckets.setdefault(
            sid,
            {
                "strategy_id": sid,
                "strategy_name": name,
                "machine_id": trade.get("machine_id"),
                "status": "unknown",
                "last_heartbeat": trade.get("time"),
                "symbols": [],
            },
        )
        pnls: list[float] = row.setdefault("_pnls", [])
        row["_count"] = int(row.get("_count") or 0) + 1
        if trade.get("pnl") is not None:
            pnls.append(float(trade["pnl"]))
        latencies: list[float] = row.setdefault("_latencies", [])
        if trade.get("latency_ms") is not None:
            latencies.append(float(trade["latency_ms"]))
        symbol = trade.get("symbol")
        if symbol and symbol not in row["symbols"]:
            row["symbols"].append(symbol)

    results = []
    for row in buckets.values():
        pnls = row.pop("_pnls", [])
        latencies = row.pop("_latencies", [])
        trade_n = row.pop("_count", 0)
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))
        results.append(
            {
                **row,
                "trade_count": trade_n if trade_n else None,
                "winning_trades": len(wins) if pnls else None,
                "losing_trades": len(losses) if pnls else None,
                "total_pnl": sum(pnls) if pnls else None,
                "win_rate": _ratio(len(wins), len(losses)),
                "profit_factor": (
                    None
                    if not pnls
                    else (gross_win / gross_loss if gross_loss else None)
                ),
                "average_win": (sum(wins) / len(wins)) if wins else None,
                "average_loss": (sum(losses) / len(losses)) if losses else None,
                "avg_latency_ms": (sum(latencies) / len(latencies)) if latencies else None,
            }
        )
    return sorted(results, key=lambda r: r["strategy_name"] or "")


def aggregate_symbols(
    trades: list[dict[str, Any]],
    strategy_name: str | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"pnls": [], "qty": None, "open": 0}
    )
    for trade in trades:
        name = str(trade.get("strategy") or "")
        if strategy_name and name != strategy_name:
            continue
        symbol = str(trade.get("symbol") or "")
        if not symbol:
            continue
        bucket = grouped[(name, symbol)]
        if trade.get("pnl") is not None:
            bucket["pnls"].append(float(trade["pnl"]))
        parts = parse_instrument(symbol)
        bucket["instrument"] = parts
        if trade.get("status") == "open":
            bucket["open"] += 1
        if trade.get("quantity") is not None:
            bucket["qty"] = trade["quantity"]

    rows = []
    for (name, symbol), bucket in grouped.items():
        pnls = bucket["pnls"]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        parts: Any = bucket["instrument"]
        gross_loss = abs(sum(losses))
        rows.append(
            {
                "strategy_name": name,
                "symbol": symbol,
                "underlying": parts.underlying,
                "instrument": parts.instrument,
                "expiry": parts.expiry,
                "strike": parts.strike,
                "option_type": parts.option_type,
                "metadata_available": parts.metadata_available,
                "trade_count": len(pnls) if pnls else None,
                "pnl": sum(pnls) if pnls else None,
                "win_rate": _ratio(len(wins), len(losses)),
                "profit_factor": (sum(wins) / gross_loss) if pnls and gross_loss else None,
                "average_trade": (sum(pnls) / len(pnls)) if pnls else None,
                "open_positions": bucket["open"] if bucket["open"] else None,
                "quantity": bucket["qty"],
            }
        )
    return sorted(rows, key=lambda r: (r["strategy_name"], r["symbol"]))
