"""What a trading device may report, and how it is validated.

A device posts JSON to one endpoint. To keep integrating a new machine trivial,
the body may be a single event, a list of events, or ``{"events": [...]}``, and
every field except ``type`` (plus ``message`` for logs/alerts) is optional.

Five event types:

- ``heartbeat`` — alive + health: cpu / ram / disk (percent), latency_ms,
  version, and any extra numeric metrics.
- ``trade`` — a fill: symbol, side, qty, price, optional pnl / strategy / order_id.
- ``positions`` — the device's full current positions list (replaces the last).
- ``log`` — level (debug|info|warning|error|critical) + message.
- ``alert`` — severity (info|warning|critical) + message.

Invalid events are rejected individually with a reason; the valid ones in the
same request are still accepted, so one bad line never loses a batch.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

EVENT_TYPES = frozenset({"heartbeat", "trade", "positions", "log", "alert"})
LOG_LEVELS = ("debug", "info", "warning", "error", "critical")
ALERT_SEVERITIES = ("info", "warning", "critical")
MAX_EVENTS_PER_REQUEST = 500
MAX_POSITIONS = 500
MAX_MESSAGE = 2000
MAX_EXTRA_METRICS = 20
MAX_KEY_LENGTH = 64


class InvalidEvent(ValueError):
    """One event could not be accepted; the message says why."""


@dataclass(frozen=True, slots=True)
class DeviceEvent:
    kind: str
    occurred_at: datetime
    severity: str  # debug|info|warning|error|critical
    message: str
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def is_notable(self) -> bool:
        """Worth an in-app notification: alerts and error-level logs."""
        return self.severity in ("error", "critical") or (
            self.kind == "alert" and self.severity == "warning"
        )


def _number(value: Any, name: str, *, lo: float | None = None, hi: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise InvalidEvent(f"{name} must be a number")
    try:
        number = float(value)
    except ValueError as error:
        raise InvalidEvent(f"{name} must be a number") from error
    if not math.isfinite(number):
        raise InvalidEvent(f"{name} must be finite")
    if (lo is not None and number < lo) or (hi is not None and number > hi):
        raise InvalidEvent(f"{name} must be between {lo} and {hi}")
    return number


def _text(value: Any, name: str, *, limit: int, required: bool = False) -> str:
    if value is None or value == "":
        if required:
            raise InvalidEvent(f"{name} is required")
        return ""
    if not isinstance(value, (str, int, float)):
        raise InvalidEvent(f"{name} must be text")
    return str(value).strip()[:limit]


def _timestamp(raw: Any, now: datetime) -> datetime:
    """ISO-8601 or unix seconds/milliseconds; absent means "now"."""
    if raw is None or raw == "":
        return now
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        seconds = raw / 1000 if raw > 10_000_000_000 else raw
        return datetime.fromtimestamp(seconds, tz=UTC)
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as error:
            raise InvalidEvent("ts must be ISO-8601 or unix time") from error
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    raise InvalidEvent("ts must be ISO-8601 or unix time")


def _heartbeat(event: dict[str, Any], occurred_at: datetime) -> DeviceEvent:
    metrics: dict[str, Any] = {}
    for name in ("cpu", "ram", "disk"):
        if event.get(name) is not None:
            metrics[name] = round(_number(event[name], name, lo=0, hi=100), 2)
    if event.get("latency_ms") is not None:
        metrics["latency_ms"] = round(_number(event["latency_ms"], "latency_ms", lo=0), 2)
    extras = event.get("metrics") or {}
    if not isinstance(extras, dict):
        raise InvalidEvent("metrics must be an object of numbers")
    for key, value in list(extras.items())[:MAX_EXTRA_METRICS]:
        metrics[str(key)[:MAX_KEY_LENGTH]] = _number(value, f"metrics.{key}")
    version = _text(event.get("version"), "version", limit=40)
    if version:
        metrics["version"] = version
    return DeviceEvent("heartbeat", occurred_at, "info", "heartbeat", metrics)


def _trade(event: dict[str, Any], occurred_at: datetime) -> DeviceEvent:
    symbol = _text(event.get("symbol"), "symbol", limit=40, required=True).upper()
    side = _text(event.get("side"), "side", limit=10, required=True).lower()
    if side not in ("buy", "sell"):
        raise InvalidEvent("side must be buy or sell")
    qty = _number(event.get("qty"), "qty", lo=0)
    trade_price = _number(event.get("price"), "price", lo=0)
    payload: dict[str, Any] = {"symbol": symbol, "side": side, "qty": qty, "price": trade_price}
    if event.get("pnl") is not None:
        payload["pnl"] = _number(event["pnl"], "pnl")
    for name in ("strategy", "order_id", "account"):
        value = _text(event.get(name), name, limit=80)
        if value:
            payload[name] = value
    message = f"{side.upper()} {qty:g} {symbol} @ {trade_price:g}"
    return DeviceEvent("trade", occurred_at, "info", message, payload)


def _positions(event: dict[str, Any], occurred_at: datetime) -> DeviceEvent:
    rows = event.get("positions")
    if not isinstance(rows, list):
        raise InvalidEvent("positions must be a list")
    if len(rows) > MAX_POSITIONS:
        raise InvalidEvent(f"at most {MAX_POSITIONS} positions per event")
    cleaned: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise InvalidEvent(f"positions[{index}] must be an object")
        position: dict[str, Any] = {
            "symbol": _text(row.get("symbol"), "symbol", limit=40, required=True).upper(),
            "qty": _number(row.get("qty"), f"positions[{index}].qty"),
        }
        for name in ("avg_price", "ltp", "pnl"):
            if row.get(name) is not None:
                position[name] = _number(row[name], f"positions[{index}].{name}")
        cleaned.append(position)
    return DeviceEvent(
        "positions",
        occurred_at,
        "info",
        f"{len(cleaned)} open position(s)",
        {"positions": cleaned},
    )


def _log(event: dict[str, Any], occurred_at: datetime) -> DeviceEvent:
    level = _text(event.get("level") or "info", "level", limit=10).lower()
    if level not in LOG_LEVELS:
        raise InvalidEvent(f"level must be one of {', '.join(LOG_LEVELS)}")
    message = _text(event.get("message"), "message", limit=MAX_MESSAGE, required=True)
    return DeviceEvent("log", occurred_at, level, message, _context(event))


def _alert(event: dict[str, Any], occurred_at: datetime) -> DeviceEvent:
    severity = _text(event.get("severity") or "warning", "severity", limit=10).lower()
    if severity not in ALERT_SEVERITIES:
        raise InvalidEvent(f"severity must be one of {', '.join(ALERT_SEVERITIES)}")
    message = _text(event.get("message"), "message", limit=MAX_MESSAGE, required=True)
    return DeviceEvent("alert", occurred_at, severity, message, _context(event))


def _context(event: dict[str, Any]) -> dict[str, Any]:
    context = event.get("context") or {}
    if not isinstance(context, dict):
        raise InvalidEvent("context must be an object")
    return {str(k)[:MAX_KEY_LENGTH]: v for k, v in list(context.items())[:MAX_EXTRA_METRICS]}


_PARSERS = {
    "heartbeat": _heartbeat,
    "trade": _trade,
    "positions": _positions,
    "log": _log,
    "alert": _alert,
}


@dataclass(frozen=True, slots=True)
class ParseResult:
    accepted: list[DeviceEvent]
    rejected: list[dict[str, Any]]  # {"index": i, "reason": "..."}


def parse_events(body: Any, *, now: datetime) -> ParseResult:
    if isinstance(body, dict) and "events" in body:
        items = body["events"]
    elif isinstance(body, list):
        items = body
    else:
        items = [body]
    if not isinstance(items, list):
        return ParseResult([], [{"index": 0, "reason": "events must be a list"}])
    if len(items) > MAX_EVENTS_PER_REQUEST:
        return ParseResult(
            [], [{"index": 0, "reason": f"at most {MAX_EVENTS_PER_REQUEST} events per request"}]
        )
    accepted: list[DeviceEvent] = []
    rejected: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        try:
            if not isinstance(item, dict):
                raise InvalidEvent("each event must be a JSON object")
            kind = str(item.get("type") or "").lower()
            if kind not in EVENT_TYPES:
                raise InvalidEvent(f"type must be one of {', '.join(sorted(EVENT_TYPES))}")
            accepted.append(_PARSERS[kind](item, _timestamp(item.get("ts"), now)))
        except InvalidEvent as error:
            rejected.append({"index": index, "reason": str(error)})
    return ParseResult(accepted, rejected)
