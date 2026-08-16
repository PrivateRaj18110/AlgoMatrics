"""Deterministic in-memory fixtures for the mock repositories.

A single seeded RNG builds every dataset once at import time so the API returns
stable data across requests. The shapes mirror ``frontend/src/types`` exactly,
so the React client behaves identically whether it reads its bundled mocks or
this backend.

When Supabase is wired up, only the repository implementations change — these
fixtures and the service/router layers above them stay put.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

_rng = random.Random(0x5A17)
_now = datetime.now(timezone.utc)


def _iso(seconds_ago: float) -> str:
    return (_now - timedelta(seconds=seconds_ago)).isoformat()


def _round(value: float, ndigits: int = 2) -> float:
    return round(value, ndigits)


SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD",
    "ETHUSD", "NAS100", "SPX500", "US30", "AUDUSD",
]
BROKER_NAMES = ["IC Markets", "Pepperstone", "Interactive Brokers", "Binance"]
ACCOUNTS = ["LIVE-001", "LIVE-002", "LIVE-003", "PROP-114"]

BASE_PRICE = {
    "EURUSD": 1.085, "GBPUSD": 1.272, "USDJPY": 156.4, "XAUUSD": 2348,
    "BTCUSD": 64210, "ETHUSD": 3420, "NAS100": 18650, "SPX500": 5430,
    "US30": 39120, "AUDUSD": 0.662,
}


# --------------------------------------------------------------------------- #
# Machines
# --------------------------------------------------------------------------- #
MACHINES: list[dict] = [
    {
        "id": "mch-london", "name": "London VPS", "location": "London · Equinix LD4",
        "provider": "Beeks Financial Cloud", "status": "online",
        "cpu": 38, "ram": 61, "disk": 47, "temperatureC": 51,
        "internetMs": 7, "brokerPingMs": 3, "pythonStatus": "online",
        "uptimeSec": 32 * 86400 + 4 * 3600, "lastHeartbeat": _iso(4), "strategyCount": 4,
    },
    {
        "id": "mch-gcloud", "name": "Google Cloud", "location": "europe-west2 · us-central1",
        "provider": "Google Cloud Platform", "status": "degraded",
        "cpu": 84, "ram": 76, "disk": 66, "temperatureC": None,
        "internetMs": 34, "brokerPingMs": 41, "pythonStatus": "online",
        "uptimeSec": 11 * 86400 + 9 * 3600, "lastHeartbeat": _iso(12), "strategyCount": 3,
    },
    {
        "id": "mch-pc", "name": "Personal Computer", "location": "Home Office · Mumbai",
        "provider": "On-premise", "status": "offline",
        "cpu": 0, "ram": 14, "disk": 73, "temperatureC": 39,
        "internetMs": 0, "brokerPingMs": 0, "pythonStatus": "offline",
        "uptimeSec": 0, "lastHeartbeat": _iso(540), "strategyCount": 2,
    },
]


def _sparkline(base: float, points: int = 24) -> list[dict]:
    acc = 0.0
    out = []
    for i in range(points):
        acc += _rng.uniform(-1, 1.15) * base
        out.append({"t": f"{i}:00", "v": _round(acc, 1)})
    return out


# --------------------------------------------------------------------------- #
# Strategies
# --------------------------------------------------------------------------- #
_STRAT_BLUEPRINTS = [
    ("Mean Reversion FX", "MR-FX", "Intraday mean reversion across major FX pairs.", "mch-london", "online"),
    ("Momentum Breakout", "MOM", "Volatility-adjusted breakout on indices.", "mch-london", "online"),
    ("Gold Scalper", "XAU-SC", "High-frequency scalping on XAUUSD.", "mch-london", "online"),
    ("Stat Arb Pairs", "ARB", "Cointegration-based statistical arbitrage.", "mch-london", "degraded"),
    ("Crypto Trend", "CT", "Multi-timeframe trend following on BTC/ETH.", "mch-gcloud", "online"),
    ("Index Overnight", "IDX-ON", "Overnight drift capture on US indices.", "mch-gcloud", "online"),
    ("News Fade", "NF", "Fades post-news overreactions on FX.", "mch-gcloud", "degraded"),
    ("Grid Hedge", "GRID", "Hedged grid on ranging majors.", "mch-pc", "offline"),
    ("Vol Harvest", "VOL", "Short-vol premium harvesting.", "mch-pc", "offline"),
]
_MACHINE_NAME = {m["id"]: m["name"] for m in MACHINES}

STRATEGIES: list[dict] = []
for i, (name, code, desc, mid, status) in enumerate(_STRAT_BLUEPRINTS):
    offline = status == "offline"
    today = 0 if offline else _round(_rng.uniform(-1800, 4200), 0)
    STRATEGIES.append({
        "id": f"str-{i + 1}", "name": name, "code": code, "description": desc,
        "status": status, "machineId": mid, "machineName": _MACHINE_NAME[mid],
        "broker": _rng.choice(BROKER_NAMES),
        "symbols": list({_rng.choice(SYMBOLS) for _ in range(_rng.randint(1, 3))}),
        "todayPnl": today,
        "weekPnl": _round(today + _rng.uniform(-3000, 9000), 0),
        "todayTrades": 0 if offline else _rng.randint(4, 64),
        "openPositions": 0 if offline else _rng.randint(0, 6),
        "winRate": _round(_rng.uniform(41, 71), 1),
        "profitFactor": _round(_rng.uniform(0.9, 2.6), 2),
        "avgLatencyMs": _round(_rng.uniform(18, 240), 0),
        "sparkline": _sparkline(_rng.uniform(60, 220)),
        "lastHeartbeat": _iso(_rng.randint(2, 600 if offline else 30)),
    })


# --------------------------------------------------------------------------- #
# Trades
# --------------------------------------------------------------------------- #
TRADES: list[dict] = []
for i in range(96):
    strat = _rng.choice(STRATEGIES)
    symbol = _rng.choice(strat["symbols"] or SYMBOLS)
    direction = "long" if _rng.random() > 0.5 else "short"
    base = BASE_PRICE.get(symbol, 100)
    digits = 1 if base > 1000 else 4
    entry = _round(base * _rng.uniform(0.995, 1.005), digits)
    is_open = _rng.random() < 0.12
    status = "open" if is_open else ("cancelled" if _rng.random() < 0.04 else "closed")
    move_r = _rng.uniform(-1.4, 1.7)
    exit_px = None if status != "closed" else _round(
        entry * (1 + (move_r if direction == "long" else -move_r) * 0.004), digits
    )
    qty = _round(_rng.uniform(0.2, 5), 2)
    directional = move_r if direction == "long" else -move_r
    pnl = 0 if status == "cancelled" else _round(directional * qty * _rng.uniform(60, 240), 0)
    minutes_ago = _rng.randint(1, 60 * 96)
    TRADES.append({
        "id": f"trd-{(96 - i):04d}", "time": _iso(minutes_ago * 60),
        "strategy": strat["name"], "machine": strat["machineName"],
        "broker": _rng.choice(BROKER_NAMES), "account": _rng.choice(ACCOUNTS),
        "symbol": symbol, "direction": direction, "entry": entry, "exit": exit_px,
        "quantity": qty, "pnl": pnl, "latencyMs": _round(_rng.uniform(14, 280), 0),
        "durationSec": _rng.randint(60, 7200) if status == "open" else _rng.randint(20, 14400),
        "status": status,
    })
TRADES.sort(key=lambda t: t["time"], reverse=True)


# --------------------------------------------------------------------------- #
# Brokers
# --------------------------------------------------------------------------- #
_BROKER_BLUEPRINTS = [
    ("brk-icm", "IC Markets", "ICMarkets-Live12", "LIVE-001", "online", 500, 4, 0.1),
    ("brk-pep", "Pepperstone", "Pepperstone-Live04", "LIVE-002", "online", 400, 7, 0.2),
    ("brk-ib", "Interactive Brokers", "IBKR-Gateway-LD4", "LIVE-003", "degraded", 50, 38, 0.4),
    ("brk-bin", "Binance", "Binance-Spot-FIX", "PROP-114", "online", 20, 22, 0.5),
]
BROKERS: list[dict] = []
for bid, name, server, acct, conn, lev, base_ping, base_spread in _BROKER_BLUEPRINTS:
    balance = _round(_rng.uniform(40000, 260000), 0)
    open_pnl = _round(_rng.uniform(-4200, 8400), 0)
    equity = _round(balance + open_pnl, 0)
    margin = _round(_rng.uniform(2000, 28000), 0)
    ping = _round(base_ping + _rng.uniform(0, base_ping), 0)
    BROKERS.append({
        "id": bid, "name": name, "server": server, "connection": conn, "account": acct,
        "spreadPips": _round(base_spread + _rng.uniform(0, 0.6), 2),
        "balance": balance, "equity": equity, "margin": margin,
        "freeMargin": _round(equity - margin, 0),
        "marginLevelPct": _round(equity / margin * 100, 0) if margin else 0,
        "leverage": lev, "openPositions": _rng.randint(0, 9),
        "pendingOrders": _rng.randint(0, 5), "rejectedOrders": _rng.randint(0, 4),
        "pingMs": ping, "lastSync": _iso(_rng.randint(1, 12)),
        "pingHistory": [
            {"t": str(i), "v": _round(max(1, base_ping + _rng.uniform(-base_ping * 0.4, base_ping * 0.6)), 1)}
            for i in range(24)
        ],
    })


# --------------------------------------------------------------------------- #
# Accounts
# --------------------------------------------------------------------------- #
_ACCOUNT_BLUEPRINTS = [
    ("acc-live-001", "LIVE-001", "IC Markets", "live", "USD", "online", 500),
    ("acc-live-002", "LIVE-002", "Pepperstone", "live", "USD", "online", 400),
    ("acc-live-003", "LIVE-003", "Interactive Brokers", "live", "GBP", "degraded", 50),
    ("acc-prop-114", "PROP-114", "Binance", "prop", "USD", "online", 20),
    ("acc-demo-001", "DEMO-001", "IC Markets", "demo", "USD", "online", 500),
]
_CODES = [s["code"] for s in STRATEGIES]
ACCOUNT_LIST: list[dict] = []
for aid, label, broker, atype, ccy, status, lev in _ACCOUNT_BLUEPRINTS:
    balance = _round(_rng.uniform(25000, 320000), 0)
    open_pnl = _round(_rng.uniform(-3600, 7200), 0)
    equity = _round(balance + open_pnl, 0)
    eq = balance * _rng.uniform(0.85, 0.95)
    curve = []
    for i in range(40):
        eq = max(eq * (1 + _rng.uniform(-0.012, 0.016)), balance * 0.7)
        curve.append({"t": str(i), "v": _round(eq, 0)})
    ACCOUNT_LIST.append({
        "id": aid, "label": label, "broker": broker, "type": atype, "currency": ccy,
        "status": status, "balance": balance, "equity": equity,
        "todayPnl": _round(_rng.uniform(-2400, 5800), 0), "openPnl": open_pnl,
        "marginLevelPct": _round(_rng.uniform(180, 2400), 0), "leverage": lev,
        "openPositions": _rng.randint(0, 8),
        "strategies": list({_rng.choice(_CODES) for _ in range(_rng.randint(1, 3))}),
        "equityCurve": curve,
    })


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
_closed = [t for t in TRADES if t["status"] == "closed"]
_open = [t for t in TRADES if t["status"] == "open"]
_wins = [t for t in _closed if t["pnl"] > 0]
_losers = [t for t in _closed if t["pnl"] < 0]


def _sum_pnl(seconds: float) -> float:
    cutoff = (_now - timedelta(seconds=seconds)).isoformat()
    return _round(sum(t["pnl"] for t in TRADES if t["time"] >= cutoff), 0)


_equity = 100000.0
_equity_curve = []
for i in range(60, -1, -1):
    _equity = max(_equity * (1 + _rng.uniform(-0.009, 0.0125)), 60000)
    d = (_now - timedelta(days=i)).date().isoformat()
    _equity_curve.append({"t": d, "v": _round(_equity, 0)})

_daily_pnl = [
    {"t": (_now - timedelta(days=29 - i)).date().isoformat(), "v": _round(_rng.uniform(-3200, 5200), 0)}
    for i in range(30)
]
_perf_base = _equity_curve[0]["v"]
_performance = [{"t": p["t"], "v": _round((p["v"] - _perf_base) / _perf_base * 100, 2)} for p in _equity_curve]

_peak = float("-inf")
_max_dd = 0.0
_cur_dd = 0.0
for p in _equity_curve:
    _peak = max(_peak, p["v"])
    dd = (p["v"] - _peak) / _peak * 100
    _cur_dd = dd
    _max_dd = min(_max_dd, dd)

_gross_win = sum(t["pnl"] for t in _wins)
_gross_loss = abs(sum(t["pnl"] for t in _losers))
_month_pnl = _round(sum(t["pnl"] for t in _closed), 0)
_equity_now = _equity_curve[-1]["v"]

DASHBOARD: dict = {
    "kpis": [
        {"id": "today_pnl", "label": "Today's PnL", "value": _sum_pnl(86400), "format": "currency", "deltaPct": 4.2, "trend": "up", "higherIsBetter": True},
        {"id": "week_pnl", "label": "Weekly PnL", "value": _sum_pnl(7 * 86400), "format": "currency", "deltaPct": 8.6, "trend": "up", "higherIsBetter": True},
        {"id": "month_pnl", "label": "Monthly PnL", "value": _month_pnl, "format": "currency", "deltaPct": 12.1, "trend": "up", "higherIsBetter": True},
        {"id": "year_pnl", "label": "Yearly PnL", "value": _round(_month_pnl * 8.2, 0), "format": "currency", "deltaPct": 21.4, "trend": "up", "higherIsBetter": True},
        {"id": "equity", "label": "Equity", "value": _equity_now, "format": "currency", "higherIsBetter": True},
        {"id": "balance", "label": "Balance", "value": _round(_equity_now - _sum_pnl(86400) * 0.3, 0), "format": "currency", "higherIsBetter": True},
        {"id": "open_positions", "label": "Open Positions", "value": len(_open), "format": "number", "higherIsBetter": True},
        {"id": "closed_trades", "label": "Closed Trades", "value": len(_closed), "format": "number", "higherIsBetter": True},
        {"id": "winning_trades", "label": "Winning Trades", "value": len(_wins), "format": "number", "higherIsBetter": True},
        {"id": "losing_trades", "label": "Losing Trades", "value": len(_losers), "format": "number", "higherIsBetter": False},
        {"id": "win_rate", "label": "Win Rate", "value": _round(len(_wins) / max(len(_closed), 1) * 100, 1), "format": "percent", "deltaPct": 1.4, "trend": "up", "higherIsBetter": True},
        {"id": "profit_factor", "label": "Profit Factor", "value": _round(_gross_win / max(_gross_loss, 1), 2), "format": "ratio", "deltaPct": 0.3, "trend": "up", "higherIsBetter": True},
        {"id": "avg_win", "label": "Average Win", "value": _round(_gross_win / max(len(_wins), 1), 0), "format": "currency", "higherIsBetter": True},
        {"id": "avg_loss", "label": "Average Loss", "value": _round(-_gross_loss / max(len(_losers), 1), 0), "format": "currency", "higherIsBetter": True},
        {"id": "exposure", "label": "Current Exposure", "value": _round(sum(t["entry"] * t["quantity"] * 1000 for t in _open), 0), "format": "currency", "higherIsBetter": False},
        {"id": "current_dd", "label": "Current Drawdown", "value": _round(_cur_dd, 1), "format": "percent", "higherIsBetter": False},
        {"id": "max_dd", "label": "Maximum Drawdown", "value": _round(_max_dd, 1), "format": "percent", "higherIsBetter": False},
    ],
    "equityCurve": _equity_curve,
    "dailyPnl": _daily_pnl,
    "performance": _performance,
}


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #
_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
_HOURS = ["08", "10", "12", "14", "16", "18", "20"]
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]


def _heatmap(rows, cols, lo, hi):
    return {
        "rows": rows, "cols": cols,
        "cells": [{"row": r, "col": c, "value": _round(_rng.uniform(lo, hi), 0)} for r in rows for c in cols],
    }


ANALYTICS: dict = {
    "dailyPnl": _daily_pnl,
    "weeklyPnl": [{"t": f"W{i + 1}", "v": _round(_rng.uniform(-6000, 15000), 0)} for i in range(12)],
    "monthlyPnl": [{"t": m, "v": _round(_rng.uniform(-8000, 42000), 0)} for m in _MONTHS],
    "winRateByStrategy": [{"label": s["code"], "value": s["winRate"]} for s in STRATEGIES],
    "profitFactorByStrategy": [{"label": s["code"], "value": s["profitFactor"]} for s in STRATEGIES],
    "latencyByMachine": [{"label": m["name"], "value": m["brokerPingMs"] or _round(_rng.uniform(20, 120), 0)} for m in MACHINES],
    "pnlHeatmap": _heatmap(_WEEKDAYS, _HOURS, -1200, 2400),
    "machineLoadHeatmap": _heatmap([m["name"] for m in MACHINES], _HOURS, 10, 98),
}


# --------------------------------------------------------------------------- #
# Risk
# --------------------------------------------------------------------------- #
def _notional() -> float:
    return _round(_rng.uniform(8000, 120000), 0)


_exposure_by_symbol = [{"label": s, "value": _notional()} for s in SYMBOLS[:7]]
_current_exposure = _round(sum(e["value"] for e in _exposure_by_symbol), 0)

RISK: dict = {
    "dailyLoss": {"label": "Daily Loss", "used": _round(_rng.uniform(1200, 6400), 0), "limit": 10000, "unit": "currency"},
    "weeklyLoss": {"label": "Weekly Loss", "used": _round(_rng.uniform(4000, 18000), 0), "limit": 30000, "unit": "currency"},
    "monthlyLoss": {"label": "Monthly Loss", "used": _round(_rng.uniform(10000, 48000), 0), "limit": 75000, "unit": "currency"},
    "currentExposure": _current_exposure,
    "maxExposure": 750000,
    "currentMargin": _round(_rng.uniform(40000, 120000), 0),
    "marginLevelPct": _round(_rng.uniform(220, 1400), 0),
    "currentDrawdownPct": _round(_rng.uniform(-8.5, -0.4), 1),
    "maxDrawdownPct": _round(_rng.uniform(-18, -10), 1),
    "valueAtRisk": _round(_rng.uniform(12000, 38000), 0),
    "exposureBySymbol": _exposure_by_symbol,
    "exposureByStrategy": [{"label": s["code"], "value": _notional()} for s in STRATEGIES if s["status"] != "offline"][:7],
    "exposureByBroker": [{"label": b["name"], "value": _notional()} for b in BROKERS],
}


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #
_STAGE_DEFS = [
    ("signal", "Signal Generated", 0), ("risk", "Risk Passed", 2),
    ("created", "Order Created", 1), ("sent", "Order Sent", 3),
    ("received", "Broker Received", 18), ("filled", "Broker Filled", 24),
    ("open", "Trade Open", 1), ("closed", "Trade Closed", 0),
]
_stages = []
_count = 1284
for i, (key, label, avg) in enumerate(_STAGE_DEFS):
    prev = _count
    drop_rate = 0.06 if key == "risk" else (0.018 if key == "filled" else 0)
    _count = prev if i == 0 else round(prev * (1 - drop_rate))
    _stages.append({
        "key": key, "label": label, "avgMs": avg, "count": _count,
        "dropped": 0 if i == 0 else prev - _count,
        "status": "warn" if avg >= 40 else "ok",
    })

_exec_recent = []
for i in range(60):
    strat = _rng.choice(STRATEGIES)
    sig, rsk, ex, brk, fil = (
        _round(_rng.uniform(1, 6), 0), _round(_rng.uniform(1, 5), 0),
        _round(_rng.uniform(2, 12), 0), _round(_rng.uniform(8, 70), 0),
        _round(_rng.uniform(10, 90), 0),
    )
    roll = _rng.random()
    _exec_recent.append({
        "id": f"exe-{(200 - i):04d}", "time": _iso(i * _rng.randint(4, 40)),
        "symbol": _rng.choice(strat["symbols"] or SYMBOLS), "strategy": strat["code"],
        "signalMs": sig, "riskMs": rsk, "execMs": ex, "brokerMs": brk, "fillMs": fil,
        "totalMs": sig + rsk + ex + brk + fil,
        "result": "filled" if roll < 0.9 else ("partial" if roll < 0.96 else "rejected"),
    })

EXECUTION: dict = {
    "stages": _stages,
    "latency": [
        {"label": "Signal Delay", "p50": 2, "p90": 5, "p95": 8, "p99": 16},
        {"label": "Execution Delay", "p50": 4, "p90": 9, "p95": 14, "p99": 27},
        {"label": "Broker Delay", "p50": 18, "p90": 41, "p95": 58, "p99": 96},
        {"label": "Fill Delay", "p50": 24, "p90": 52, "p95": 73, "p99": 132},
        {"label": "Total Delay", "p50": 48, "p90": 104, "p95": 148, "p99": 268},
    ],
    "recent": _exec_recent,
    "throughput": [{"t": str(i), "v": _rng.randint(4, 38)} for i in range(60)],
}


# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #
ALERTS: list[dict] = [
    {"id": "alt-1", "type": "machine_offline", "severity": "critical", "title": "Machine offline",
     "message": "Personal Computer has missed 9 consecutive heartbeats.", "source": "Personal Computer",
     "time": _iso(540), "acknowledged": False},
    {"id": "alt-2", "type": "strategy_crash", "severity": "critical", "title": "Strategy crashed",
     "message": "Grid Hedge (GRID) exited unexpectedly with code 1.", "source": "Personal Computer · GRID",
     "time": _iso(660), "acknowledged": False},
    {"id": "alt-3", "type": "high_cpu", "severity": "warning", "title": "High CPU load",
     "message": "Google Cloud CPU sustained above 85% for 6 minutes.", "source": "Google Cloud",
     "time": _iso(240), "acknowledged": False},
    {"id": "alt-4", "type": "high_latency", "severity": "warning", "title": "Elevated broker latency",
     "message": "News Fade (NF) broker round-trip exceeded 250ms.", "source": "Google Cloud · NF",
     "time": _iso(420), "acknowledged": False},
    {"id": "alt-5", "type": "high_ram", "severity": "warning", "title": "Memory pressure",
     "message": "Google Cloud RAM usage climbing — 79% utilised.", "source": "Google Cloud",
     "time": _iso(960), "acknowledged": True},
    {"id": "alt-6", "type": "broker_offline", "severity": "critical", "title": "Broker session dropped",
     "message": "Binance FIX session re-connected after a 3s outage.", "source": "Google Cloud · Crypto Trend",
     "time": _iso(2520), "acknowledged": True},
    {"id": "alt-7", "type": "high_latency", "severity": "info", "title": "Latency normalised",
     "message": "London VPS broker ping back under 5ms.", "source": "London VPS",
     "time": _iso(3480), "acknowledged": True},
]


# --------------------------------------------------------------------------- #
# Logs
# --------------------------------------------------------------------------- #
_LOG_TEMPLATES = [
    ("application", "info", "api.gateway", "GET /api/dashboard/overview 200 in 18ms"),
    ("application", "info", "ws.broadcast", "Pushed overview snapshot to 3 clients"),
    ("application", "warn", "api.ratelimit", "Client 10.0.0.4 approaching rate limit (88/100)"),
    ("strategy", "info", "MR-FX", "Signal generated: SELL EURUSD size=1.2"),
    ("strategy", "info", "MOM", "Position opened LONG NAS100 @ 18642.5"),
    ("strategy", "warn", "GRID", "Grid level 7 reached — pausing new entries"),
    ("strategy", "error", "GRID", "Strategy exited unexpectedly with code 1"),
    ("python", "debug", "monitor_sdk", "heartbeat() flushed 1 metric batch"),
    ("python", "info", "runtime", "Python 3.13 runtime started, pid=20488"),
    ("python", "error", "asyncio", "Task exception: ConnectionResetError(10054)"),
    ("broker", "info", "mt5.bridge", "MT5 terminal connected — ICMarkets-Live12"),
    ("broker", "warn", "mt5.bridge", "Requote on order #88213, retrying"),
    ("broker", "error", "fix.session", "FIX session dropped, reconnecting in 3s"),
    ("database", "info", "supabase.pool", "Connection pool established (size=10)"),
    ("database", "debug", "supabase.query", "INSERT trades (id, pnl) committed in 4ms"),
    ("system", "info", "host.london", "CPU 41% · RAM 62% · disk 47%"),
    ("system", "warn", "host.gcloud", "CPU sustained >85% for 6m"),
    ("system", "error", "host.pc", "Heartbeat timeout — host marked offline"),
]
LOGS: list[dict] = []
for i in range(220):
    source, level, logger, message = _rng.choice(_LOG_TEMPLATES)
    LOGS.append({
        "id": f"log-{(2200 - i):05d}", "time": _iso(i * _rng.randint(2, 18)),
        "source": source, "level": level, "logger": logger, "message": message,
    })
LOGS.sort(key=lambda x: x["time"], reverse=True)


# --------------------------------------------------------------------------- #
# Events (live terminal)
# --------------------------------------------------------------------------- #
_EVENT_TEMPLATES = [
    ("trade", "info", lambda: (_rng.choice(["MR-FX", "MOM", "XAU-SC"]), f"Trade opened {'LONG' if _rng.random() > 0.5 else 'SHORT'} {_rng.choice(SYMBOLS)}")),
    ("trade", "info", lambda: (_rng.choice(["MR-FX", "CT"]), f"Trade closed {_rng.choice(SYMBOLS)} · PnL {_round((_rng.random() - 0.4) * 1800, 0)}")),
    ("strategy", "info", lambda: (_rng.choice(["MR-FX", "MOM"]), "Strategy started")),
    ("strategy", "warning", lambda: (_rng.choice(["GRID", "VOL"]), "Strategy stopped by operator")),
    ("machine", "warning", lambda: (_rng.choice(["London VPS", "Google Cloud"]), f"High CPU load {_rng.randint(86, 98)}%")),
    ("machine", "critical", lambda: ("Personal Computer", "Machine offline — heartbeat lost")),
    ("broker", "info", lambda: (_rng.choice(BROKER_NAMES), "Broker connected")),
    ("broker", "warning", lambda: (_rng.choice(BROKER_NAMES), f"Elevated latency {_rng.randint(180, 420)}ms")),
    ("database", "info", lambda: ("Supabase", "Database connected")),
    ("system", "critical", lambda: (_rng.choice(["MR-FX", "NF"]), "Python exception: ConnectionResetError")),
    ("risk", "warning", lambda: ("Risk Engine", f"Exposure {_rng.randint(60, 92)}% of daily cap")),
]


def build_event(seconds_ago: float, event_id: str) -> dict:
    category, severity, builder = _rng.choice(_EVENT_TEMPLATES)
    source, message = builder()
    return {
        "id": event_id, "time": _iso(seconds_ago), "category": category,
        "severity": severity, "source": source, "message": message,
    }


EVENTS: list[dict] = sorted(
    [build_event(i * _rng.randint(8, 40), f"evt-{(800 - i):04d}") for i in range(80)],
    key=lambda e: e["time"], reverse=True,
)
