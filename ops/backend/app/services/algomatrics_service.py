"""Live platform data from the AlgoMatrics control plane.

Each public function returns a payload shaped exactly like the corresponding
mock fixture (the routers' ``response_model`` validates it), or ``None`` when
live mode is disabled or the control plane is unreachable — in which case the
router falls back to the mock repositories.

Field-mapping notes
-------------------
The platform models a multi-tenant SaaS (orders, fills, positions, runs); the
ops dashboard models a personal trading floor (machines, brokers, latency).
Where the platform has no equivalent signal (per-fill PnL, margin, latency,
sparklines) the mapping uses zeros/empty series rather than inventing data.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from app.clients.algomatrics import AlgoMatricsUnavailable, get_algomatrics_client

logger = logging.getLogger(__name__)

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _f(value: Any, default: float = 0.0) -> float:
    """Coerce Decimal-as-string / number / None into a float."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _iso(value: Any) -> str:
    return str(value) if value else datetime.now(timezone.utc).isoformat()


def _short(uuid_str: Any) -> str:
    return str(uuid_str)[:8]


def _live(fetch: Any) -> Any:
    """Run ``fetch()`` against the control plane; ``None`` disables live mode."""
    client = get_algomatrics_client()
    if client is None:
        return None
    try:
        return fetch(client)
    except AlgoMatricsUnavailable as exc:
        logger.warning("AlgoMatrics unavailable, serving mock data: %s", exc)
        return None
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Unexpected AlgoMatrics payload, serving mock data: %s", exc)
        return None


# --------------------------------------------------------------------------- #
# Shared lookups
# --------------------------------------------------------------------------- #
def _account_index(client: Any) -> dict[str, dict]:
    """Map account id → account payload."""
    return {str(a["id"]): a for a in client.get_json("/accounts")}


def _connection_index(client: Any) -> dict[str, dict]:
    """Map connection id → connection payload."""
    return {str(c["id"]): c for c in client.get_json("/broker-connections")}


def _broker_for_account(account: dict | None, connections: dict[str, dict]) -> str:
    if account is None:
        return "algomatrics"
    connection = connections.get(str(account.get("connection_id")))
    return str(connection["broker_code"]) if connection else "algomatrics"


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
def dashboard_overview() -> dict | None:
    return _live(_dashboard_overview)


def _dashboard_overview(client: Any) -> dict:
    summary = client.get_json("/dashboard/summary")
    perf = client.get_json("/analytics/summary")
    curve = client.get_json("/portfolio/equity-curve", {"days": 90})
    daily = client.get_json("/analytics/daily-pnl")

    def kpi(
        kpi_id: str,
        label: str,
        value: float,
        fmt: str,
        *,
        higher_is_better: bool | None = None,
    ) -> dict:
        trend = "up" if value > 0 else "down" if value < 0 else "flat"
        return {
            "id": kpi_id,
            "label": label,
            "value": value,
            "format": fmt,
            "deltaPct": None,
            "trend": trend,
            "higherIsBetter": higher_is_better,
        }

    kpis = [
        kpi("total-equity", "Total Equity", _f(summary["total_equity"]), "currency"),
        kpi("total-cash", "Cash", _f(summary["total_cash"]), "currency"),
        kpi("today-pnl", "Today PnL", _f(summary["realized_pnl_today"]), "currency", higher_is_better=True),
        kpi("unrealized-pnl", "Open PnL", _f(summary["unrealized_pnl"]), "currency", higher_is_better=True),
        kpi("open-positions", "Open Positions", float(summary["open_positions"]), "number"),
        kpi("open-orders", "Open Orders", float(summary["open_orders"]), "number"),
        kpi("active-strategies", "Active Strategies", float(summary["active_strategies"]), "number"),
        kpi("trades-today", "Trades Today", float(summary["trades_today"]), "number"),
        kpi("win-rate", "Win Rate", _f(perf["win_rate_pct"]), "percent", higher_is_better=True),
        kpi("profit-factor", "Profit Factor", _f(perf.get("profit_factor")), "ratio", higher_is_better=True),
        kpi("sharpe", "Sharpe", _f(perf["sharpe_ratio"]), "ratio", higher_is_better=True),
        kpi("max-drawdown", "Max Drawdown", _f(perf["max_drawdown_pct"]), "percent", higher_is_better=False),
    ]

    equity_curve = [{"t": _iso(p["as_of"]), "v": _f(p["equity"])} for p in curve]
    daily_pnl = [{"t": str(d["day"]), "v": _f(d["realized_pnl"])} for d in daily]

    performance: list[dict] = []
    running = 0.0
    for point in daily_pnl:
        running += point["v"]
        performance.append({"t": point["t"], "v": running})

    return {
        "kpis": kpis,
        "equityCurve": equity_curve,
        "dailyPnl": daily_pnl,
        "performance": performance,
    }


# --------------------------------------------------------------------------- #
# Strategies
# --------------------------------------------------------------------------- #
def strategies() -> list[dict] | None:
    return _live(_strategies)


def _strategies(client: Any) -> list[dict]:
    platform_strategies = client.get_json("/strategies")
    runs = client.get_json("/strategy-runs")
    accounts = _account_index(client)
    connections = _connection_index(client)

    runs_by_strategy: dict[str, list[dict]] = {}
    for run in runs:
        runs_by_strategy.setdefault(str(run["strategy_id"]), []).append(run)

    rows: list[dict] = []
    for strategy in platform_strategies:
        sid = str(strategy["id"])
        strategy_runs = runs_by_strategy.get(sid, [])
        states = {str(r.get("state", "")) for r in strategy_runs}

        if "error" in states or any(r.get("error") for r in strategy_runs):
            status = "degraded"
        elif int(strategy.get("active_runs", 0)) > 0 or "running" in states:
            status = "online"
        else:
            status = "offline"

        stats_pnl = sum(
            _f(r.get("stats", {}).get("realized_pnl", r.get("stats", {}).get("pnl")))
            for r in strategy_runs
        )
        stats_trades = sum(int(_f(r.get("stats", {}).get("trades"))) for r in strategy_runs)

        broker = "algomatrics"
        if strategy_runs:
            account = accounts.get(str(strategy_runs[0].get("account_id")))
            broker = _broker_for_account(account, connections)

        heartbeats = [str(r["last_heartbeat_at"]) for r in strategy_runs if r.get("last_heartbeat_at")]
        code = "".join(word[0] for word in str(strategy["name"]).split() if word)[:6].upper() or "ALGO"

        rows.append(
            {
                "id": sid,
                "name": str(strategy["name"]),
                "code": code,
                "description": str(strategy.get("description", "")),
                "status": status,
                "machineId": "algomatrics",
                "machineName": "AlgoMatrics Cloud",
                "broker": broker,
                "symbols": [],
                "todayPnl": stats_pnl,
                "weekPnl": stats_pnl,
                "todayTrades": stats_trades,
                "openPositions": 0,
                "winRate": 0.0,
                "profitFactor": 0.0,
                "avgLatencyMs": 0.0,
                "sparkline": [],
                "lastHeartbeat": max(heartbeats) if heartbeats else _iso(strategy.get("updated_at")),
            }
        )
    return rows


def strategy(strategy_id: str) -> dict | None:
    rows = strategies()
    if rows is None:
        return None
    return next((r for r in rows if r["id"] == strategy_id), None)


# --------------------------------------------------------------------------- #
# Trades
# --------------------------------------------------------------------------- #
def trades(limit: int | None = None) -> list[dict] | None:
    return _live(lambda client: _trades(client, limit))


def _trades(client: Any, limit: int | None) -> list[dict]:
    page = client.get_json("/trades", {"limit": min(limit or 200, 200)})
    accounts = _account_index(client)
    connections = _connection_index(client)

    rows: list[dict] = []
    for fill in page["items"]:
        account = accounts.get(str(fill["account_id"]))
        rows.append(
            {
                "id": str(fill["id"]),
                "time": _iso(fill["executed_at"]),
                "strategy": "Platform",
                "machine": "AlgoMatrics Cloud",
                "broker": _broker_for_account(account, connections),
                "account": str(account["name"]) if account else _short(fill["account_id"]),
                "symbol": str(fill["symbol"]),
                "direction": "long" if str(fill["side"]).lower() == "buy" else "short",
                "entry": _f(fill["price"]),
                "exit": None,
                "quantity": _f(fill["quantity"]),
                "pnl": -_f(fill["fee"]),
                "latencyMs": 0.0,
                "durationSec": 0,
                "status": "closed",
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# Risk
# --------------------------------------------------------------------------- #
def risk_overview() -> dict | None:
    return _live(_risk_overview)


def _risk_overview(client: Any) -> dict:
    limits = client.get_json("/risk/limits")
    summary = client.get_json("/dashboard/summary")
    perf = client.get_json("/analytics/summary")
    daily = client.get_json("/analytics/daily-pnl")
    exposure = client.get_json("/analytics/exposure")
    curve = client.get_json("/portfolio/equity-curve", {"days": 90})

    # Prefer the active organization-wide limit (account_id null).
    active = [l for l in limits if l.get("is_active")]
    org_limit = next((l for l in active if l.get("account_id") is None), None) or (
        active[0] if active else (limits[0] if limits else {})
    )
    max_daily_loss = _f(org_limit.get("max_daily_loss"), 1_000.0)

    def loss_used(days: int) -> float:
        recent = sorted(daily, key=lambda d: str(d["day"]))[-days:]
        pnl = sum(_f(d["realized_pnl"]) for d in recent)
        return max(0.0, -pnl)

    total_equity = _f(summary["total_equity"])
    equities = [_f(p["equity"]) for p in curve]
    peak = max(equities) if equities else total_equity
    current_dd_pct = ((peak - total_equity) / peak * 100.0) if peak > 0 else 0.0

    by_symbol: dict[str, float] = {}
    for row in exposure:
        symbol = str(row.get("symbol", "?"))
        by_symbol[symbol] = by_symbol.get(symbol, 0.0) + _f(row.get("market_value"))
    current_exposure = sum(by_symbol.values())

    # 1-day 95% parametric VaR from the platform's daily return volatility.
    value_at_risk = total_equity * _f(perf["daily_return_volatility_pct"]) / 100.0 * 1.65

    return {
        "dailyLoss": {
            "label": "Daily loss",
            "used": max(0.0, -_f(summary["realized_pnl_today"])),
            "limit": max_daily_loss,
            "unit": "currency",
        },
        # Weekly/monthly limits are trading-day multiples of the daily limit —
        # the platform only defines a daily loss limit.
        "weeklyLoss": {
            "label": "Weekly loss",
            "used": loss_used(7),
            "limit": max_daily_loss * 5,
            "unit": "currency",
        },
        "monthlyLoss": {
            "label": "Monthly loss",
            "used": loss_used(30),
            "limit": max_daily_loss * 20,
            "unit": "currency",
        },
        "currentExposure": current_exposure,
        "maxExposure": _f(org_limit.get("max_exposure_value"), max(current_exposure, 1.0)),
        "currentMargin": 0.0,
        "marginLevelPct": 0.0,
        "currentDrawdownPct": current_dd_pct,
        "maxDrawdownPct": _f(org_limit.get("max_drawdown_pct"), _f(perf["max_drawdown_pct"])),
        "valueAtRisk": value_at_risk,
        "exposureBySymbol": [
            {"label": symbol, "value": value} for symbol, value in sorted(by_symbol.items())
        ],
        "exposureByStrategy": [],
        "exposureByBroker": [],
    }


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #
def analytics() -> dict | None:
    return _live(_analytics)


def _analytics(client: Any) -> dict:
    daily = client.get_json("/analytics/daily-pnl")
    monthly = client.get_json("/analytics/monthly-pnl")

    daily_pnl = [{"t": str(d["day"]), "v": _f(d["realized_pnl"])} for d in daily]

    weekly: dict[str, float] = {}
    heat_cells: list[dict] = []
    heat_cols: list[str] = []
    for entry in daily:
        day = date.fromisoformat(str(entry["day"]))
        iso = day.isocalendar()
        week_label = f"{iso.year}-W{iso.week:02d}"
        weekly[week_label] = weekly.get(week_label, 0.0) + _f(entry["realized_pnl"])
        if week_label not in heat_cols:
            heat_cols.append(week_label)
        heat_cells.append(
            {
                "row": _WEEKDAYS[day.weekday()],
                "col": week_label,
                "value": _f(entry["realized_pnl"]),
            }
        )

    return {
        "dailyPnl": daily_pnl,
        "weeklyPnl": [{"t": week, "v": value} for week, value in sorted(weekly.items())],
        "monthlyPnl": [{"t": str(m["month"]), "v": _f(m["realized_pnl"])} for m in monthly],
        # Per-strategy and per-machine breakdowns are not exposed by the
        # platform API yet; the charts render their empty states.
        "winRateByStrategy": [],
        "profitFactorByStrategy": [],
        "latencyByMachine": [],
        "pnlHeatmap": {
            "rows": _WEEKDAYS,
            "cols": heat_cols[-8:],
            "cells": [c for c in heat_cells if c["col"] in heat_cols[-8:]],
        },
        "machineLoadHeatmap": {"rows": [], "cols": [], "cells": []},
    }


# --------------------------------------------------------------------------- #
# Brokers
# --------------------------------------------------------------------------- #
def brokers() -> list[dict] | None:
    return _live(_brokers)


def _brokers(client: Any) -> list[dict]:
    connections = client.get_json("/broker-connections")

    status_map = {"verified": "online", "active": "online", "failed": "offline", "error": "offline"}
    rows: list[dict] = []
    for connection in connections:
        accounts = connection.get("accounts", [])
        balance = sum(_f(a["cash_balance"]) for a in accounts)
        equity = sum(_f(a["equity"]) for a in accounts)
        rows.append(
            {
                "id": str(connection["id"]),
                "name": str(connection.get("name") or connection["broker_name"]),
                "server": str(connection["broker_code"]),
                "connection": status_map.get(str(connection["status"]).lower(), "degraded"),
                "account": str(accounts[0]["external_account_id"]) if accounts else "—",
                "spreadPips": 0.0,
                "balance": balance,
                "equity": equity,
                "margin": 0.0,
                "freeMargin": balance,
                "marginLevelPct": 0.0,
                "leverage": 1,
                "openPositions": 0,
                "pendingOrders": 0,
                "rejectedOrders": 0,
                "pingMs": 0.0,
                "lastSync": _iso(connection.get("last_verified_at") or connection.get("created_at")),
                "pingHistory": [],
            }
        )
    return rows


def broker(broker_id: str) -> dict | None:
    rows = brokers()
    if rows is None:
        return None
    return next((r for r in rows if r["id"] == broker_id), None)


# --------------------------------------------------------------------------- #
# Accounts
# --------------------------------------------------------------------------- #
def accounts() -> list[dict] | None:
    return _live(_accounts)


def _accounts(client: Any) -> list[dict]:
    platform_accounts = client.get_json("/accounts")
    connections = _connection_index(client)

    rows: list[dict] = []
    for account in platform_accounts:
        curve = client.get_json(
            "/portfolio/equity-curve", {"days": 30, "account_id": str(account["id"])}
        )
        today_pnl = 0.0
        open_pnl = 0.0
        if curve:
            last = curve[-1]
            open_pnl = _f(last["unrealized_pnl"])
            if len(curve) >= 2:
                prev = curve[-2]
                today_pnl = (_f(last["realized_pnl"]) + open_pnl) - (
                    _f(prev["realized_pnl"]) + _f(prev["unrealized_pnl"])
                )

        rows.append(
            {
                "id": str(account["id"]),
                "label": str(account["name"]),
                "broker": _broker_for_account(account, connections),
                "type": "live" if str(account["mode"]).lower() == "live" else "demo",
                "currency": str(account["base_currency"]),
                "status": "online" if str(account["status"]).lower() == "active" else "offline",
                "balance": _f(account["cash_balance"]),
                "equity": _f(account["equity"]),
                "todayPnl": today_pnl,
                "openPnl": open_pnl,
                "marginLevelPct": 0.0,
                "leverage": 1,
                "openPositions": 0,
                "strategies": [],
                "equityCurve": [{"t": _iso(p["as_of"]), "v": _f(p["equity"])} for p in curve],
            }
        )
    return rows


def account(account_id: str) -> dict | None:
    rows = accounts()
    if rows is None:
        return None
    return next((r for r in rows if r["id"] == account_id), None)
