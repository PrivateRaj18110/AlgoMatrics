from __future__ import annotations

from typing import Any

from algo_platform.modules.operations.application.analytics import (
    aggregate_strategies,
    aggregate_symbols,
)
from algo_platform.modules.operations.infrastructure.telemetry_store import TelemetryStore


class OperationsService:
    def __init__(self, store: TelemetryStore) -> None:
        self._store = store

    def machines(self) -> list[dict[str, Any]]:
        return self._store.list_machines()

    def events(self, **filters: Any) -> list[dict[str, Any]]:
        return self._store.list_events(**filters)

    def logs(self, limit: int = 200) -> list[dict[str, Any]]:
        return self._store.list_logs(limit=limit)

    def closed_trades(self, **filters: Any) -> list[dict[str, Any]]:
        rows = self._store.list_trades(**filters)
        return [row for row in rows if str(row.get("status") or "").lower() == "closed"]

    def orders(self, **filters: Any) -> list[dict[str, Any]]:
        return self._store.list_events(event_type="order", **filters)

    def alerts(self, limit: int = 200) -> list[dict[str, Any]]:
        return [
            event
            for event in self._store.list_events(limit=limit)
            if event.get("event_type") in {"alert", "error"} or event.get("severity") == "critical"
        ]

    def strategies(self) -> list[dict[str, Any]]:
        trades = self._store.list_trades(limit=1000)
        status = self._store.list_events(limit=400, event_type="strategy_status")
        return aggregate_strategies(trades, status)

    def strategy_symbols(self, strategy_name: str | None = None) -> list[dict[str, Any]]:
        trades = self._store.list_trades(limit=1000, strategy=strategy_name)
        return aggregate_symbols(trades, strategy_name)

    def overview(self) -> dict[str, Any]:
        machines = self.machines()
        trades = self.closed_trades(limit=500)
        pnls = [float(t["pnl"]) for t in trades if t.get("pnl") is not None]
        return {
            "machine_count": len(machines) if machines else None,
            "online_machines": (
                sum(1 for m in machines if m.get("status") == "online") if machines else None
            ),
            "closed_trade_count": len(trades) if trades else None,
            "total_pnl": sum(pnls) if pnls else None,
            "awaiting_telemetry": not machines and not trades,
        }
