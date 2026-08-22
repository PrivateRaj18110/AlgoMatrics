"""Heartbeat construction.

Every few seconds the agent emits a heartbeat so the dashboard knows the machine
is alive. The heartbeat carries machine identity, the Python version, a UTC
timestamp and a compact health summary derived from the latest metrics snapshot.

This module only *builds* the payload; the agent's scheduler decides when to send
it (see :class:`raj_monitor.agent.Agent`).
"""

from __future__ import annotations

import platform
from typing import Any

from .types import now_iso


def build_heartbeat(
    *,
    machine: str,
    agent_id: str,
    metrics: dict[str, Any] | None = None,
    strategy_count: int = 0,
) -> dict[str, Any]:
    """Compose a heartbeat payload from the most recent metrics snapshot."""
    metrics = metrics or {}
    health = _health(metrics)
    return {
        "agentId": agent_id,
        "machine": machine,
        "python": platform.python_version(),
        "ts": now_iso(),
        "health": health,
        "cpu": metrics.get("cpu", 0.0),
        "ram": metrics.get("ram", 0.0),
        "disk": metrics.get("disk", 0.0),
        "internetMs": metrics.get("internetMs", 0.0),
        "brokerPingMs": metrics.get("brokerPingMs", metrics.get("latencyMs", 0.0)),
        "uptimeSec": metrics.get("uptimeSec", 0),
        "mt5Running": metrics.get("mt5Running", False),
        "strategyCount": strategy_count,
    }


def _health(metrics: dict[str, Any]) -> str:
    """Coarse health bucket the dashboard maps to a status colour."""
    if not metrics.get("internetOk", True):
        return "degraded"
    cpu = float(metrics.get("cpu", 0.0))
    ram = float(metrics.get("ram", 0.0))
    if cpu >= 95 or ram >= 95:
        return "critical"
    if cpu >= 85 or ram >= 90:
        return "degraded"
    return "healthy"
