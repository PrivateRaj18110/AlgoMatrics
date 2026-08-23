"""Read models derived only from ingested Google telemetry.

Production strategy/broker/account lists must not come from ``mock_data`` or
from the SaaS control plane. Identity is the string the engine actually sent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.mock_policy import (
    DEMO_ACCOUNT_NAMES,
    DEMO_BROKER_NAMES,
    DEMO_MACHINE_IDS,
    DEMO_MACHINE_NAMES,
    DEMO_STRATEGY_NAMES,
    allow_mock_fixtures,
)
from app.database.session import database_enabled
from app.repositories import events_repo, trades_repo


def strategy_identity(name: str, machine_id: str | None) -> str:
    """Stable identity: one row per (strategy name, machine).

    Google does not emit a dimension table. Multiple envelopes with the same
    name on the same machine are the same instance. The same name on two
    machines is two instances.
    """
    clean = (name or "").strip()
    if not clean:
        return ""
    host = (machine_id or "").strip() or "unknown"
    return f"{host}::{clean}"


def is_suspect_blotter_row(trade: dict[str, Any]) -> bool:
    """Likely misclassified heartbeat/status rows (f9bee1a era). Do not delete."""
    strategy = str(trade.get("strategy") or "").strip().lower()
    entry = trade.get("entry")
    exit_px = trade.get("exit")
    pnl = trade.get("pnl")
    duration = trade.get("durationSec", trade.get("duration_sec", 0))
    status = str(trade.get("status") or "").lower()
    return (
        strategy in {"", "unknown"}
        and (entry == 0 or entry == 0.0)
        and exit_px in (None, "")
        and (pnl == 0 or pnl == 0.0)
        and (duration == 0 or duration == 0.0)
        and status == "closed"
    )


def _status_from_payload(summary: str | None) -> str:
    text = (summary or "").lower()
    if "offline" in text or "stopped" in text:
        return "offline"
    if "degraded" in text or "warn" in text:
        return "degraded"
    if "online" in text or "running" in text or "healthy" in text:
        return "online"
    return "unknown"


def telemetry_strategies() -> list[dict]:
    """Strategies reported on envelopes / strategy_status / real trades."""
    if not database_enabled() and not allow_mock_fixtures():
        return []
    names: dict[str, dict[str, Any]] = {}

    query = getattr(events_repo, "query", None)
    events = (
        query(limit=400, event_type="strategy_status")
        if callable(query)
        else [e for e in events_repo.list() if e.get("eventType") == "strategy_status"]
    )
    for event in events:
        name = str(event.get("strategy") or "").strip()
        if not name:
            continue
        machine_id = event.get("machineId") or event.get("machine_id")
        if not allow_mock_fixtures():
            if str(machine_id or "").lower() in DEMO_MACHINE_IDS:
                continue
        sid = strategy_identity(name, machine_id)
        row = names.setdefault(
            sid,
            {
                "id": sid,
                "name": name,
                "code": name,
                "description": "Reported by Google telemetry",
                "status": _status_from_payload(event.get("payloadSummary") or event.get("payload_summary")),
                "machineId": machine_id or "",
                "machineName": event.get("source") or machine_id or "",
                "broker": "",
                "symbols": [],
                "todayPnl": None,
                "weekPnl": None,
                "todayTrades": None,
                "openPositions": None,
                "winRate": None,
                "profitFactor": None,
                "avgLatencyMs": None,
                "sparkline": [],
                "lastHeartbeat": event.get("time"),
            },
        )
        row["lastHeartbeat"] = event.get("time") or row.get("lastHeartbeat")
        row["status"] = _status_from_payload(event.get("payloadSummary") or event.get("payload_summary"))

    for trade in trades_repo.list():
        if is_suspect_blotter_row(trade):
            continue
        name = str(trade.get("strategy") or "").strip()
        if not name or name.lower() == "unknown":
            continue
        machine_id = trade.get("machine_id") or trade.get("machineId")
        machine_name = trade.get("machine") or ""
        if not allow_mock_fixtures():
            if (
                str(machine_id or "").lower() in DEMO_MACHINE_IDS
                or str(machine_name).lower() in DEMO_MACHINE_NAMES
            ):
                continue
        sid = strategy_identity(name, str(machine_id) if machine_id else None)
        symbol = str(trade.get("symbol") or "").strip()
        row = names.setdefault(
            sid,
            {
                "id": sid,
                "name": name,
                "code": name,
                "description": "Reported by Google telemetry",
                "status": "unknown",
                "machineId": machine_id or "",
                "machineName": machine_name or machine_id or "",
                "broker": trade.get("broker") or "",
                "symbols": [],
                "todayPnl": None,
                "weekPnl": None,
                "todayTrades": None,
                "openPositions": None,
                "winRate": None,
                "profitFactor": None,
                "avgLatencyMs": None,
                "sparkline": [],
                "lastHeartbeat": trade.get("time"),
            },
        )
        if symbol and symbol not in row["symbols"]:
            row["symbols"].append(symbol)
        if trade.get("broker") and not row["broker"]:
            row["broker"] = trade["broker"]

    return list(names.values())


def telemetry_brokers() -> list[dict]:
    """Distinct broker names that actually appear on telemetry trades."""
    if not database_enabled() and not allow_mock_fixtures():
        return []
    seen: dict[str, dict] = {}
    for trade in trades_repo.list():
        if is_suspect_blotter_row(trade):
            continue
        name = str(trade.get("broker") or "").strip()
        if not name:
            continue
        if not allow_mock_fixtures() and name.lower() in DEMO_BROKER_NAMES:
            continue
        seen[name] = {
            "id": name,
            "name": name,
            "server": "Not reported",
            "connection": "unknown",
            "account": trade.get("account") or "",
            "spreadPips": None,
            "balance": None,
            "equity": None,
            "margin": None,
            "freeMargin": None,
            "marginLevelPct": None,
            "leverage": None,
            "openPositions": None,
            "pendingOrders": None,
            "rejectedOrders": None,
            "pingMs": None,
            "lastSync": trade.get("time"),
            "pingHistory": [],
        }
    return list(seen.values())


def telemetry_accounts() -> list[dict]:
    if not database_enabled() and not allow_mock_fixtures():
        return []
    seen: dict[str, dict] = {}
    for trade in trades_repo.list():
        if is_suspect_blotter_row(trade):
            continue
        account = str(trade.get("account") or "").strip()
        if not account:
            continue
        if not allow_mock_fixtures() and account.lower() in DEMO_ACCOUNT_NAMES:
            continue
        seen[account] = {
            "id": account,
            "label": account,
            "broker": trade.get("broker") or "",
            "type": "live",
            "currency": "INR",
            "status": "unknown",
            "balance": None,
            "equity": None,
            "todayPnl": None,
            "openPnl": None,
            "marginLevelPct": None,
            "leverage": None,
            "openPositions": None,
            "strategies": [trade["strategy"]] if trade.get("strategy") else [],
            "equityCurve": [],
        }
    return list(seen.values())


def utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
