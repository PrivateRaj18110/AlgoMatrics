"""Aggregate API router.

Every feature router is registered here so ``main.py`` only ever includes a
single router. All endpoints are live; data is served from the in-memory mock
repositories until Supabase is wired up.
"""

from fastapi import APIRouter

from app.api.routers import (
    accounts,
    agent,
    alerts,
    analytics,
    brokers,
    dashboard,
    events,
    execution,
    health,
    ingest,
    logs,
    machines,
    risk,
    settings,
    strategies,
    trades,
    ws,
)

api_router = APIRouter()

# System
api_router.include_router(health.router)
api_router.include_router(ws.router)

# Trading
api_router.include_router(dashboard.router, prefix="/dashboard")
api_router.include_router(strategies.router, prefix="/strategies")
api_router.include_router(trades.router, prefix="/trades")
api_router.include_router(execution.router, prefix="/execution")
api_router.include_router(risk.router, prefix="/risk")
api_router.include_router(analytics.router, prefix="/analytics")

# Infrastructure
api_router.include_router(machines.router, prefix="/machines")
api_router.include_router(brokers.router, prefix="/brokers")
api_router.include_router(accounts.router, prefix="/accounts")

# Operations
api_router.include_router(events.router, prefix="/events")
api_router.include_router(logs.router, prefix="/logs")
api_router.include_router(alerts.router, prefix="/alerts")
api_router.include_router(settings.router, prefix="/settings")

# SDK ingestion (monitor_sdk — legacy direct path, retained for compatibility)
api_router.include_router(ingest.router, prefix="/ingest")

# Raj Local Agent ingestion (one agent per machine -> backend)
api_router.include_router(agent.router, prefix="/agent")
