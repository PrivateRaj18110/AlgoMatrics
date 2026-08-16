"""Aggregate API router.

Every feature router is registered here so ``main.py`` only ever includes a
single router. All endpoints are live; repository implementations are selected
by runtime configuration so local mock mode and durable ops-database mode share
the same API contract.
"""

from fastapi import APIRouter, Depends

from app.api.dependencies.dashboard_auth import require_dashboard_viewer
from app.api.routers import (
    accounts,
    agent,
    alerts,
    analytics,
    brokers,
    dashboard,
    eod,
    events,
    execution,
    health,
    ingest,
    logs,
    machines,
    quant,
    recovery,
    risk,
    sessions,
    settings,
    strategies,
    trades,
    ws,
)

api_router = APIRouter()
dashboard_read_dependencies = [Depends(require_dashboard_viewer)]

# System
api_router.include_router(health.router)
api_router.include_router(ws.router)

# Trading
api_router.include_router(
    dashboard.router, prefix="/dashboard", dependencies=dashboard_read_dependencies
)
api_router.include_router(
    strategies.router, prefix="/strategies", dependencies=dashboard_read_dependencies
)
api_router.include_router(
    trades.router, prefix="/trades", dependencies=dashboard_read_dependencies
)
api_router.include_router(
    execution.router, prefix="/execution", dependencies=dashboard_read_dependencies
)
api_router.include_router(risk.router, prefix="/risk", dependencies=dashboard_read_dependencies)
api_router.include_router(
    analytics.router, prefix="/analytics", dependencies=dashboard_read_dependencies
)

# Infrastructure
api_router.include_router(
    machines.router, prefix="/machines", dependencies=dashboard_read_dependencies
)
api_router.include_router(
    brokers.router, prefix="/brokers", dependencies=dashboard_read_dependencies
)
api_router.include_router(
    accounts.router, prefix="/accounts", dependencies=dashboard_read_dependencies
)

# Operations
api_router.include_router(eod.router, prefix="/eod")
api_router.include_router(events.router, prefix="/events", dependencies=dashboard_read_dependencies)
api_router.include_router(quant.router, prefix="/quant", dependencies=dashboard_read_dependencies)
api_router.include_router(
    recovery.router, prefix="/recovery", dependencies=dashboard_read_dependencies
)
api_router.include_router(
    sessions.router, prefix="/sessions", dependencies=dashboard_read_dependencies
)
api_router.include_router(logs.router, prefix="/logs", dependencies=dashboard_read_dependencies)
api_router.include_router(alerts.router, prefix="/alerts", dependencies=dashboard_read_dependencies)
api_router.include_router(
    settings.router, prefix="/settings", dependencies=dashboard_read_dependencies
)

# SDK ingestion (monitor_sdk — legacy direct path, retained for compatibility)
api_router.include_router(ingest.router, prefix="/ingest")

# Raj Local Agent ingestion (one agent per machine -> backend)
api_router.include_router(agent.router, prefix="/agent")
