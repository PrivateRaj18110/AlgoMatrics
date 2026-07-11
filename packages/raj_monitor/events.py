"""Event, trade and log payload builders + light validation.

Centralises the shape of every ``data`` body the SDK produces so the SDK methods
stay tiny and the agent/backend can rely on consistent fields. Validation is
forgiving: unknown values are coerced to safe defaults rather than rejected,
because dropping a trade event over a typo would defeat the point of monitoring.
"""

from __future__ import annotations

from typing import Any

from . import constants


def normalize_severity(severity: str | None) -> str:
    """Map an arbitrary severity onto the backend's info/warning/critical set."""
    s = (severity or "info").lower()
    if s in ("error", "critical", "fatal"):
        return constants.SEVERITY_CRITICAL
    if s in ("warn", "warning"):
        return constants.SEVERITY_WARNING
    return constants.SEVERITY_INFO


def normalize_category(category: str | None) -> str:
    c = (category or "strategy").lower()
    return c if c in constants.EVENT_CATEGORIES else "strategy"


def normalize_log_level(level: str | None) -> str:
    lv = (level or "info").lower()
    if lv in ("warning", "warn"):
        return "warn"
    if lv in ("error", "critical", "fatal"):
        return "error"
    if lv == "debug":
        return "debug"
    return "info"


def build_event(message: str, category: str = "strategy", severity: str = "info") -> dict[str, Any]:
    return {
        "message": str(message),
        "category": normalize_category(category),
        "severity": normalize_severity(severity),
    }


def build_error(message: str, traceback: str | None = None, context: dict | None = None) -> dict[str, Any]:
    return {
        "message": str(message),
        "traceback": traceback,
        "context": context or {},
        "severity": constants.SEVERITY_CRITICAL,
        "category": "system",
    }


def build_log(message: str, level: str = "info", logger: str = "strategy") -> dict[str, Any]:
    return {
        "message": str(message),
        "level": normalize_log_level(level),
        "logger": str(logger),
    }


def build_trade(**kw: Any) -> dict[str, Any]:
    """Build a trade event body.

    Supports the full trade lifecycle via ``action``: open, close, modify,
    pending, cancelled, rejected. Direction is normalised to long/short.
    """
    action = str(kw.get("action", kw.get("status", "close"))).lower()
    if action not in constants.TRADE_ACTIONS:
        action = "close"
    direction = str(kw.get("direction", "long")).lower()
    if direction in ("buy", "long"):
        direction = "long"
    elif direction in ("sell", "short"):
        direction = "short"
    out = {
        "symbol": kw.get("symbol", "UNKNOWN"),
        "action": action,
        "direction": direction,
        "entry": _num(kw.get("entry")),
        "exit": _num(kw.get("exit")) if kw.get("exit") is not None else None,
        "quantity": _num(kw.get("quantity", kw.get("qty", 0))),
        "pnl": _num(kw.get("pnl", 0.0)),
        "latencyMs": _num(kw.get("latencyMs", kw.get("latency_ms", 0.0))),
        "durationSec": int(_num(kw.get("durationSec", kw.get("duration_sec", 0)))),
        "orderId": kw.get("orderId", kw.get("order_id")),
        "reason": kw.get("reason"),
    }
    return {k: v for k, v in out.items() if v is not None}


def build_position(**kw: Any) -> dict[str, Any]:
    direction = str(kw.get("direction", "long")).lower()
    direction = "short" if direction in ("sell", "short") else "long"
    return {
        "symbol": kw.get("symbol", "UNKNOWN"),
        "direction": direction,
        "quantity": _num(kw.get("quantity", kw.get("qty", 0))),
        "entry": _num(kw.get("entry", 0.0)),
        "unrealizedPnl": _num(kw.get("unrealizedPnl", kw.get("unrealized_pnl", 0.0))),
    }


def build_metric(name: str, value: float, unit: str | None = None) -> dict[str, Any]:
    return {"name": str(name), "value": _num(value), "unit": unit}


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
