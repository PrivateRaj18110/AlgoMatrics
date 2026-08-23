"""Production must never serve demo fixtures.

Development and tests may still use in-memory mock repositories. Production
(``ENVIRONMENT=production``) fails closed to empty payloads instead.
"""

from __future__ import annotations

from app.core.config import get_settings


DEMO_MACHINE_IDS = frozenset({"mch-london", "mch-gcloud", "mch-pc"})
DEMO_MACHINE_NAMES = frozenset({"london vps", "personal computer"})
DEMO_STRATEGY_NAMES = frozenset(
    {
        "mean reversion fx",
        "momentum breakout",
        "gold scalper",
        "stat arb pairs",
        "crypto trend",
        "index overnight",
        "news fade",
        "grid hedge",
        "vol harvest",
    }
)
DEMO_BROKER_NAMES = frozenset({"ic markets", "pepperstone", "interactive brokers", "binance"})
DEMO_ACCOUNT_NAMES = frozenset({"live-001", "live-002", "live-003", "prop-114", "demo-001"})


def allow_mock_fixtures() -> bool:
    """True only outside production.

    Do not key this off a frontend flag. A mis-set ``VITE_USE_MOCK`` must not
    resurrect London VPS / Gold Scalper rows in a live cluster.
    """
    return not get_settings().is_production



def empty_dashboard() -> dict:
    return {"kpis": [], "equityCurve": [], "dailyPnl": [], "performance": []}


def empty_analytics() -> dict:
    return {
        "dailyPnl": [],
        "weeklyPnl": [],
        "monthlyPnl": [],
        "winRateByStrategy": [],
        "profitFactorByStrategy": [],
        "latencyByMachine": [],
        "pnlHeatmap": {"rows": [], "cols": [], "cells": []},
        "machineLoadHeatmap": {"rows": [], "cols": [], "cells": []},
    }


def empty_risk() -> dict:
    return {
        "dailyLoss": {"label": "Daily loss", "used": None, "limit": None, "unit": "currency"},
        "weeklyLoss": {"label": "Weekly loss", "used": None, "limit": None, "unit": "currency"},
        "monthlyLoss": {"label": "Monthly loss", "used": None, "limit": None, "unit": "currency"},
        "currentExposure": None,
        "maxExposure": None,
        "currentMargin": None,
        "marginLevelPct": None,
        "currentDrawdownPct": None,
        "maxDrawdownPct": None,
        "valueAtRisk": None,
        "exposureBySymbol": [],
        "exposureByStrategy": [],
        "exposureByBroker": [],
    }


def empty_execution() -> dict:
    return {"stages": [], "latency": [], "recent": [], "throughput": []}
