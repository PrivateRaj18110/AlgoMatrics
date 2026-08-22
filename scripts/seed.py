"""Idempotent seed data: plan catalog, broker catalog, instrument master.

Everything inserted here is explicitly SEED DATA required for the platform to
operate (plans and broker catalog) plus a starter instrument universe for the
paper-trading simulator. Rows are upserted by their natural keys, so the
script is safe to run on every deployment.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.config import get_settings
from algo_platform.modules.billing.infrastructure.models import PlanModel
from algo_platform.modules.brokerage.infrastructure.models import BrokerModel
from algo_platform.modules.instruments.infrastructure.models import (
    InstrumentModel,
)
from algo_platform.shared.domain.types import utc_now
from algo_platform.shared.infrastructure.database import (
    create_engine,
    create_session_factory,
)

PLANS: list[dict[str, Any]] = [
    {
        "code": "free",
        "name": "Free",
        "description": "Get started with paper trading and one strategy.",
        "price_monthly": Decimal("0"),
        "price_yearly": Decimal("0"),
        "currency": "INR",
        "trial_days": 0,
        "sort_order": 0,
        "features": [
            "1 broker connection (paper)",
            "1 active strategy",
            "20 orders per day",
            "Community support",
        ],
        "limits": {
            "max_broker_connections": 1,
            "max_active_strategies": 1,
            "max_orders_per_day": 20,
            "max_members": 1,
            "max_watchlists": 3,
            "api_access": False,
            "live_trading": False,
        },
    },
    {
        "code": "starter",
        "name": "Starter",
        "description": "For active paper traders validating strategies.",
        "price_monthly": Decimal("999"),
        "price_yearly": Decimal("9990"),
        "currency": "INR",
        "trial_days": 14,
        "sort_order": 1,
        "features": [
            "2 broker connections",
            "3 active strategies",
            "200 orders per day",
            "API access",
            "3 team members",
            "E-mail support",
        ],
        "limits": {
            "max_broker_connections": 2,
            "max_active_strategies": 3,
            "max_orders_per_day": 200,
            "max_members": 3,
            "max_watchlists": 10,
            "api_access": True,
            "live_trading": False,
        },
    },
    {
        "code": "pro",
        "name": "Pro",
        "description": "Live trading, more automation, and a full team.",
        "price_monthly": Decimal("2499"),
        "price_yearly": Decimal("24990"),
        "currency": "INR",
        "trial_days": 14,
        "sort_order": 2,
        "features": [
            "5 broker connections",
            "10 active strategies",
            "1,000 orders per day",
            "Live trading",
            "API access",
            "10 team members",
            "Priority support",
        ],
        "limits": {
            "max_broker_connections": 5,
            "max_active_strategies": 10,
            "max_orders_per_day": 1000,
            "max_members": 10,
            "max_watchlists": 25,
            "api_access": True,
            "live_trading": True,
        },
    },
    {
        "code": "enterprise",
        "name": "Enterprise",
        "description": "Unlimited scale, custom onboarding, and SLAs.",
        "price_monthly": Decimal("9999"),
        "price_yearly": Decimal("99990"),
        "currency": "INR",
        "trial_days": 0,
        "sort_order": 3,
        "features": [
            "Unlimited broker connections",
            "Unlimited strategies",
            "Unlimited orders",
            "Live trading",
            "Unlimited team members",
            "Dedicated support and SLA",
        ],
        "limits": {
            "max_broker_connections": -1,
            "max_active_strategies": -1,
            "max_orders_per_day": -1,
            "max_members": -1,
            "max_watchlists": -1,
            "api_access": True,
            "live_trading": True,
        },
    },
]

BROKERS: list[dict[str, Any]] = [
    {
        "code": "paper",
        "name": "Paper Trading",
        "description": "Built-in deterministic simulator with configurable balance.",
        "supports_paper": True,
        "supports_live": False,
        "capabilities": {
            "order_types": ["market", "limit", "stop", "stop_limit"],
            "asset_classes": ["equity", "index", "crypto", "forex"],
        },
        "credential_fields": [
            {
                "name": "starting_balance",
                "label": "Starting balance",
                "secret": False,
                "help_text": "Simulated cash the account starts with (e.g. 1000000).",
            },
            {
                "name": "base_currency",
                "label": "Base currency",
                "secret": False,
                "help_text": "Three-letter code, e.g. INR or USD.",
            },
        ],
    },
    {
        "code": "zerodha",
        "name": "Zerodha Kite",
        "description": "NSE/BSE equities and F&O via Kite Connect.",
        "supports_paper": False,
        "supports_live": True,
        "capabilities": {
            "order_types": ["market", "limit", "stop", "stop_limit"],
            "asset_classes": ["equity", "futures", "options"],
            "exchange": "NSE",
        },
        "credential_fields": [
            {"name": "api_key", "label": "API key", "secret": False},
            {"name": "api_secret", "label": "API secret", "secret": True},
            {
                "name": "access_token",
                "label": "Access token",
                "secret": True,
                "help_text": "Daily access token from the Kite Connect login flow.",
            },
        ],
    },
    {
        "code": "angelone",
        "name": "Angel One SmartAPI",
        "description": "NSE/BSE trading via Angel One SmartAPI.",
        "supports_paper": False,
        "supports_live": True,
        "capabilities": {
            "order_types": ["market", "limit", "stop", "stop_limit"],
            "asset_classes": ["equity", "futures", "options"],
            "exchange": "NSE",
        },
        "credential_fields": [
            {"name": "api_key", "label": "API key", "secret": False},
            {"name": "client_code", "label": "Client code", "secret": False},
            {
                "name": "jwt_token",
                "label": "Session JWT",
                "secret": True,
                "help_text": "JWT from the SmartAPI login/TOTP flow.",
            },
        ],
    },
    {
        "code": "flattrade",
        "name": "Flattrade",
        "description": "NSE/BSE equities and F&O via the free Flattrade API.",
        "supports_paper": False,
        "supports_live": True,
        "capabilities": {
            "order_types": ["market", "limit", "stop", "stop_limit"],
            "asset_classes": ["equity", "futures", "options"],
            "exchange": "NSE",
        },
        "credential_fields": [
            {"name": "client_code", "label": "Client code", "secret": False},
            {
                "name": "session_token",
                "label": "API session token",
                "secret": True,
                "help_text": "Daily token (jKey) from the Flattrade API login flow.",
            },
        ],
    },
]

# Venues pulled from the catalog for now (intraday India focus). Adapters stay
# in the codebase; the seed deactivates any existing catalog rows so they stop
# appearing in the UI and new connections cannot be created.
RETIRED_BROKER_CODES: list[str] = ["delta", "mt5", "binance", "interactive_brokers"]

# SEED DATA: starter instrument universe for the paper simulator.
INSTRUMENTS: list[tuple[str, str, str, str, str, str, str, str]] = [
    # symbol, name, exchange, asset_class, currency, tick, lot, reference price
    ("RELIANCE", "Reliance Industries", "NSE", "equity", "INR", "0.05", "1", "2900"),
    ("TCS", "Tata Consultancy Services", "NSE", "equity", "INR", "0.05", "1", "3850"),
    ("HDFCBANK", "HDFC Bank", "NSE", "equity", "INR", "0.05", "1", "1650"),
    ("INFY", "Infosys", "NSE", "equity", "INR", "0.05", "1", "1480"),
    ("ICICIBANK", "ICICI Bank", "NSE", "equity", "INR", "0.05", "1", "1190"),
    ("SBIN", "State Bank of India", "NSE", "equity", "INR", "0.05", "1", "830"),
    ("TATAMOTORS", "Tata Motors", "NSE", "equity", "INR", "0.05", "1", "980"),
    ("ITC", "ITC Limited", "NSE", "equity", "INR", "0.05", "1", "440"),
    ("WIPRO", "Wipro", "NSE", "equity", "INR", "0.05", "1", "520"),
    ("ADANIENT", "Adani Enterprises", "NSE", "equity", "INR", "0.05", "1", "3150"),
    ("NIFTY50", "Nifty 50 Index", "NSE", "index", "INR", "0.05", "25", "24200"),
    ("BANKNIFTY", "Bank Nifty Index", "NSE", "index", "INR", "0.05", "15", "52400"),
    ("BTCUSDT", "Bitcoin / USDT", "DELTA", "crypto", "USD", "0.5", "0.001", "67000"),
    ("ETHUSDT", "Ethereum / USDT", "DELTA", "crypto", "USD", "0.05", "0.01", "3500"),
    ("SOLUSDT", "Solana / USDT", "DELTA", "crypto", "USD", "0.01", "0.1", "155"),
    ("XRPUSDT", "Ripple / USDT", "DELTA", "crypto", "USD", "0.0001", "1", "0.52"),
    ("EURUSD", "Euro / US Dollar", "FX", "forex", "USD", "0.00001", "1000", "1.085"),
    ("GBPUSD", "Pound / US Dollar", "FX", "forex", "USD", "0.00001", "1000", "1.27"),
    ("USDJPY", "US Dollar / Yen", "FX", "forex", "USD", "0.001", "1000", "158.2"),
    ("USDINR", "US Dollar / Rupee", "FX", "forex", "INR", "0.0025", "1000", "83.5"),
]


async def seed_plans(session: AsyncSession) -> int:
    created = 0
    for spec in PLANS:
        existing = (
            await session.execute(select(PlanModel).where(PlanModel.code == spec["code"]))
        ).scalar_one_or_none()
        if existing is not None:
            continue
        session.add(
            PlanModel(
                id=uuid.uuid4(),
                code=spec["code"],
                name=spec["name"],
                description=spec["description"],
                price_monthly=spec["price_monthly"],
                price_yearly=spec["price_yearly"],
                currency=spec["currency"],
                features=spec["features"],
                limits=spec["limits"],
                trial_days=spec["trial_days"],
                is_active=True,
                sort_order=spec["sort_order"],
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
        created += 1
    return created


async def seed_brokers(session: AsyncSession) -> int:
    created = 0
    for code in RETIRED_BROKER_CODES:
        retired = (
            await session.execute(select(BrokerModel).where(BrokerModel.code == code))
        ).scalar_one_or_none()
        if retired is not None and retired.is_active:
            retired.is_active = False
    for spec in BROKERS:
        existing = (
            await session.execute(select(BrokerModel).where(BrokerModel.code == spec["code"]))
        ).scalar_one_or_none()
        if existing is not None:
            if not existing.is_active and spec["code"] not in RETIRED_BROKER_CODES:
                existing.is_active = True
            continue
        session.add(
            BrokerModel(
                id=uuid.uuid4(),
                code=spec["code"],
                name=spec["name"],
                description=spec["description"],
                credential_fields=spec["credential_fields"],
                capabilities=spec["capabilities"],
                supports_paper=spec["supports_paper"],
                supports_live=spec["supports_live"],
                is_active=True,
                created_at=utc_now(),
            )
        )
        created += 1
    return created


async def seed_instruments(session: AsyncSession) -> int:
    created = 0
    for symbol, name, exchange, asset_class, currency, tick, lot, reference in INSTRUMENTS:
        existing = (
            await session.execute(select(InstrumentModel).where(InstrumentModel.symbol == symbol))
        ).scalar_one_or_none()
        if existing is not None:
            continue
        session.add(
            InstrumentModel(
                symbol=symbol,
                name=name,
                exchange=exchange,
                asset_class=asset_class,
                currency=currency,
                tick_size=Decimal(tick),
                lot_size=Decimal(lot),
                price_precision=4,
                reference_price=Decimal(reference),
                is_active=True,
                created_at=utc_now(),
            )
        )
        created += 1
    return created


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_size=2)
    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        plans = await seed_plans(session)
        brokers = await seed_brokers(session)
        instruments = await seed_instruments(session)
        await session.commit()
    await engine.dispose()
    print(
        f"seed complete: plans+{plans} brokers+{brokers} instruments+{instruments} "
        "(existing rows untouched)"
    )


if __name__ == "__main__":
    asyncio.run(main())
