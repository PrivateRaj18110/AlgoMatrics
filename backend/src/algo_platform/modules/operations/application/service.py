from __future__ import annotations

from typing import Any

from algo_platform.modules.operations.application.instrument import parse_instrument
from algo_platform.modules.operations.domain.identity import strategy_identity
from algo_platform.modules.operations.infrastructure.telemetry_store import TelemetryStore
from algo_platform.shared.domain.errors import UnavailableError

TIMESTAMP_CONTRACT = {
    "event_ts": "events.time (producer/event clock, UTC)",
    "ingest_ts": "events.created_at (ops-api insert clock, UTC)",
    "trade_ts": "trades.time (event time on the classified trade row, UTC)",
    "exchange_ts": "not present in current Google envelopes; always null",
    "received_ts": "same as ingest_ts when created_at is stored",
}


def _win_rate(wins: int, losses: int) -> float | None:
    if wins + losses == 0:
        return None
    return wins / (wins + losses)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


class OperationsService:
    def __init__(self, store: TelemetryStore, *, app_env: str = "local") -> None:
        self._store = store
        self._app_env = app_env

    def ensure_available(self) -> None:
        if self._app_env == "production" and not self._store.configured:
            raise UnavailableError("OPS_DATABASE_URL is not configured")

    def machines(self) -> list[dict[str, Any]]:
        self.ensure_available()
        return self._store.list_machines()

    def events(self, **filters: Any) -> list[dict[str, Any]]:
        self.ensure_available()
        return self._store.list_events(**filters)

    def logs(self, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        self.ensure_available()
        return self._store.list_logs(limit=limit, offset=offset)

    def closed_trades(self, **filters: Any) -> list[dict[str, Any]]:
        self.ensure_available()
        filters.setdefault("status", "closed")
        return self._store.list_trades(**filters)

    def orders(self, **filters: Any) -> list[dict[str, Any]]:
        self.ensure_available()
        return self._store.list_events(event_type="order", **filters)

    def alerts(self, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        self.ensure_available()
        return self._store.list_events(limit=limit, offset=offset, alert_only=True)

    def strategies(self) -> list[dict[str, Any]]:
        self.ensure_available()
        if not self._store.configured:
            return []
        grouped = self._store.aggregate_trade_groups(group_by="strategy")
        status = self._store.list_events(limit=400, event_type="strategy_status")
        symbol_rows = self._store.aggregate_trade_groups(group_by="strategy_symbol")
        machines = self._store.list_machines()
        machine_status_map = {m["id"]: m.get("status") for m in machines}
        symbols_by_strategy: dict[str, list[str]] = {}
        for row in symbol_rows:
            name = row.get("strategy_name")
            symbol = row.get("symbol")
            if name and symbol:
                bucket = symbols_by_strategy.setdefault(str(name), [])
                if symbol not in bucket:
                    bucket.append(str(symbol))
        status_by_id: dict[str, dict[str, Any]] = {}
        for event in status:
            name = event.get("strategy")
            sid = strategy_identity(name, event.get("machine_id"))
            if not sid:
                continue
            status_by_id[sid] = event
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in grouped:
            name = row.get("strategy_name")
            if not name:
                continue
            m_id = row.get("machine_id")
            sid = strategy_identity(name, m_id)
            seen.add(sid)
            wins = _int_or_none(row.get("winning_trades")) or 0
            losses = _int_or_none(row.get("losing_trades")) or 0
            trade_n = _int_or_none(row.get("trade_count"))
            event = status_by_id.get(sid, {})
            m_status = machine_status_map.get(m_id) if m_id else None
            results.append(
                {
                    "strategy_id": sid,
                    "strategy_name": name,
                    "machine_id": m_id,
                    "status": self._status_from_event(event, m_status),
                    "last_heartbeat": event.get("time"),
                    "symbols": symbols_by_strategy.get(str(name), []),
                    "trade_count": trade_n,
                    "winning_trades": wins if trade_n else None,
                    "losing_trades": losses if trade_n else None,
                    "total_pnl": _float_or_none(row.get("gross_pnl")),
                    "gross_pnl": _float_or_none(row.get("gross_pnl")),
                    "average_trade": _float_or_none(row.get("average_trade")),
                    "best_trade": _float_or_none(row.get("best_trade")),
                    "worst_trade": _float_or_none(row.get("worst_trade")),
                    "win_rate": _win_rate(wins, losses),
                    "avg_latency_ms": _float_or_none(row.get("avg_latency_ms")),
                }
            )
        for sid, event in status_by_id.items():
            if sid in seen:
                continue
            name = event.get("strategy")
            m_id = event.get("machine_id")
            m_status = machine_status_map.get(m_id) if m_id else None
            results.append(
                {
                    "strategy_id": sid,
                    "strategy_name": name,
                    "machine_id": m_id,
                    "status": self._status_from_event(event, m_status),
                    "last_heartbeat": event.get("time"),
                    "symbols": [],
                    "trade_count": None,
                    "winning_trades": None,
                    "losing_trades": None,
                    "total_pnl": None,
                    "gross_pnl": None,
                    "average_trade": None,
                    "best_trade": None,
                    "worst_trade": None,
                    "win_rate": None,
                    "avg_latency_ms": None,
                }
            )
        return sorted(results, key=lambda r: r["strategy_name"] or "")

    def strategy_symbols(self, strategy_name: str | None = None) -> list[dict[str, Any]]:
        self.ensure_available()
        if not self._store.configured:
            return []
        grouped = self._store.aggregate_trade_groups(
            group_by="strategy_symbol", strategy=strategy_name
        )
        return [self._symbol_row(row) for row in grouped if row.get("symbol")]

    def symbol_strategies(self, symbol: str | None = None) -> list[dict[str, Any]]:
        self.ensure_available()
        if not self._store.configured:
            return []
        grouped = self._store.aggregate_trade_groups(
            group_by="symbol_strategy", symbol=symbol
        )
        rows = [self._symbol_row(row) for row in grouped if row.get("symbol")]
        return sorted(rows, key=lambda r: (r["symbol"] or "", r["strategy_name"] or ""))

    def analytics(self, strategy: str | None = None) -> dict[str, Any]:
        return {
            "strategies": self.strategies()
            if strategy is None
            else [row for row in self.strategies() if row["strategy_name"] == strategy],
            "symbols": self.strategy_symbols(strategy),
            "by_symbol": self.symbol_strategies(),
            "option_metadata": (
                "optional_parse_of_symbol_when_NIFTY_strike_CEPE_pattern; "
                "producer does not send underlying/strike/expiry/option_type/instrument_token"
            ),
            "timestamps": TIMESTAMP_CONTRACT,
        }

    def overview(self) -> dict[str, Any]:
        self.ensure_available()
        machines = self.machines()
        trades = self.closed_trades(limit=500)
        pnls = [float(t["pnl"]) for t in trades if t.get("pnl") is not None]
        configured = self._store.configured
        return {
            "machine_count": len(machines) if machines else (0 if configured else None),
            "online_machines": (
                sum(1 for m in machines if m.get("status") == "online")
                if machines
                else (0 if configured else None)
            ),
            "closed_trade_count": len(trades) if trades else (0 if configured else None),
            "total_pnl": sum(pnls) if pnls else (0.0 if configured and trades else None),
            "awaiting_telemetry": configured and not machines and not trades,
            "telemetry_configured": configured,
        }

    @staticmethod
    def _status_from_event(
        event: dict[str, Any], machine_status: str | None = None
    ) -> str:
        if machine_status in ("offline", "stopped"):
            return "offline"
        summary = str(event.get("payload_summary") or "").lower()
        if "running" in summary or "online" in summary:
            return "online" if machine_status != "offline" else "offline"
        if "stop" in summary or "offline" in summary:
            return "offline"
        return "unknown"

    def _symbol_row(self, row: dict[str, Any]) -> dict[str, Any]:
        symbol = row.get("symbol")
        parts = parse_instrument(str(symbol) if symbol else None)
        wins = _int_or_none(row.get("winning_trades")) or 0
        losses = _int_or_none(row.get("losing_trades")) or 0
        trade_n = _int_or_none(row.get("trade_count"))
        return {
            "strategy_name": row.get("strategy_name"),
            "symbol": symbol,
            "underlying": parts.underlying,
            "instrument": parts.instrument,
            "expiry": parts.expiry,
            "strike": parts.strike,
            "option_type": parts.option_type,
            "metadata_available": parts.metadata_available,
            "trade_count": trade_n,
            "winning_trades": wins if trade_n else None,
            "losing_trades": losses if trade_n else None,
            "pnl": _float_or_none(row.get("gross_pnl")),
            "average_trade": _float_or_none(row.get("average_trade")),
            "best_trade": _float_or_none(row.get("best_trade")),
            "worst_trade": _float_or_none(row.get("worst_trade")),
            "win_rate": _win_rate(wins, losses),
        }
