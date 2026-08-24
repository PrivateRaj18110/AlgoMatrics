"""Canonical dispatch kind for agent telemetry envelopes.

Google DataAgent / RajBridge may send ``event_type`` / ``source_event_type``
(and historically wrap mixed telemetry as ``kind=trade``). Closed-trade blotter
rows are created only for an explicit trade classification — never because a
payload happens to contain direction, symbol, strategy, or an order field.

The Google PerformanceMonitor map is preserved here for AWS-side routing only:

    heartbeat          → heartbeat
    signal             → strategy_status
    order              → order
    trade_closed       → trade
    api_call           → system_status
    counter            → system_status
    hybrid_v2_metric   → system_status
"""

from __future__ import annotations

from typing import Any, Mapping

# Google PerformanceMonitor._DATA_AGENT_EVENT_MAP. Do not change Google-side
# transport; this only interprets what already arrives on AWS.
SOURCE_EVENT_TYPE_MAP = {
    "heartbeat": "heartbeat",
    "signal": "strategy_status",
    "order": "order",
    "trade_closed": "trade",
    "api_call": "system_status",
    "counter": "system_status",
    "hybrid_v2_metric": "system_status",
    "system_health": "system_health",
}

TRADE_KINDS = frozenset({"trade", "trade_closed"})

NON_TRADE_KINDS = frozenset({
    "heartbeat", "metrics", "metric", "event", "error",
    "position", "start", "stop", "log",
    "system_status", "strategy_status", "signal", "order", "fill",
    "pnl", "risk", "sync_status", "recovery", "system_health",
})


def canonicalize_type(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return SOURCE_EVENT_TYPE_MAP.get(text, text)


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _nested_dicts(data: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    blob = _mapping(data)
    if blob is None:
        return []
    out: list[Mapping[str, Any]] = [blob]
    for key in ("payload", "data"):
        nested = _mapping(blob.get(key))
        if nested is not None:
            out.append(nested)
    return out


def iter_type_hints(env: Any) -> list[str]:
    """Ordered type hints: Google fields first, wrapper ``kind`` last."""
    data = getattr(env, "data", None)
    if not isinstance(data, Mapping):
        extra = getattr(env, "model_extra", None)
        data = extra if isinstance(extra, Mapping) else {}

    hints: list[Any] = [
        getattr(env, "source_event_type", None),
        getattr(env, "event_type", None),
    ]
    extra = getattr(env, "model_extra", None)
    if isinstance(extra, Mapping):
        hints.extend([extra.get("source_event_type"), extra.get("event_type"), extra.get("eventType")])

    for blob in _nested_dicts(data if isinstance(data, Mapping) else None):
        hints.extend([
            blob.get("source_event_type"),
            blob.get("sourceEventType"),
            blob.get("event_type"),
            blob.get("eventType"),
        ])

    hints.append(getattr(env, "kind", None))
    for blob in _nested_dicts(data if isinstance(data, Mapping) else None):
        hints.append(blob.get("kind"))
        hints.append(blob.get("type"))

    out: list[str] = []
    seen: set[str] = set()
    for raw in hints:
        canon = canonicalize_type(raw)
        if canon is None or canon in seen:
            continue
        seen.add(canon)
        out.append(canon)
    return out


GENERIC_KINDS = frozenset({"event"})


def resolve_dispatch_kind(env: Any) -> str | None:
    """Return the canonical envelope kind used for ingest routing.

    A specific non-trade Google/DataAgent type always wins over a wrapper
    ``kind=trade``. Generic ``event`` does not override ``trade`` /
    ``trade_closed``. Legacy ``kind=trade`` still creates a trade when no
    contradicting type is present.
    """
    hints = iter_type_hints(env)
    for hint in hints:
        if hint in NON_TRADE_KINDS and hint not in GENERIC_KINDS:
            return hint
    for hint in hints:
        if hint in TRADE_KINDS:
            return "trade"
    for hint in hints:
        if hint in NON_TRADE_KINDS:
            return hint
    return hints[0] if hints else None


def is_trade_kind(kind: str | None) -> bool:
    return canonicalize_type(kind) == "trade"
