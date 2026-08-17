from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from algo_platform.api.dependencies.core import SettingsDep
from algo_platform.api.dependencies.tenant import TenantContext, require_permission
from algo_platform.modules.operations.application.service import OperationsService
from algo_platform.modules.operations.infrastructure.telemetry_store import TelemetryStore
from algo_platform.modules.organizations.domain.roles import Permission

router = APIRouter(tags=["operations"])

OpsTenant = Annotated[TenantContext, Depends(require_permission(Permission.TRADING_VIEW))]


def get_operations_service(settings: SettingsDep) -> OperationsService:
    return OperationsService(TelemetryStore(settings.ops_database_url))


OpsDep = Annotated[OperationsService, Depends(get_operations_service)]


@router.get("/operations/overview")
def operations_overview(_tenant: OpsTenant, service: OpsDep) -> dict[str, Any]:
    return service.overview()


@router.get("/operations/machines")
def operations_machines(_tenant: OpsTenant, service: OpsDep) -> list[dict[str, Any]]:
    return service.machines()


@router.get("/operations/events")
def operations_events(
    _tenant: OpsTenant,
    service: OpsDep,
    limit: int = Query(200, ge=1, le=400),
    event_type: str | None = Query(default=None),
    machine_id: str | None = Query(default=None),
    strategy: str | None = None,
    symbol: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict[str, Any]]:
    return service.events(
        limit=limit,
        event_type=event_type,
        machine_id=machine_id,
        strategy=strategy,
        symbol=symbol,
        since=since,
        until=until,
    )


@router.get("/operations/logs")
def operations_logs(
    _tenant: OpsTenant,
    service: OpsDep,
    limit: int = Query(200, ge=1, le=400),
) -> list[dict[str, Any]]:
    return service.logs(limit=limit)


@router.get("/operations/alerts")
def operations_alerts(_tenant: OpsTenant, service: OpsDep) -> list[dict[str, Any]]:
    return service.alerts()


@router.get("/operations/orders")
def operations_orders(
    _tenant: OpsTenant,
    service: OpsDep,
    limit: int = Query(200, ge=1, le=400),
    machine_id: str | None = None,
    strategy: str | None = None,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    return service.orders(limit=limit, machine_id=machine_id, strategy=strategy, symbol=symbol)


@router.get("/operations/trades")
def operations_trades(
    _tenant: OpsTenant,
    service: OpsDep,
    limit: int = Query(200, ge=1, le=1000),
    strategy: str | None = None,
    symbol: str | None = None,
    machine_id: str | None = None,
) -> list[dict[str, Any]]:
    return service.closed_trades(
        limit=limit, strategy=strategy, symbol=symbol, machine_id=machine_id
    )


@router.get("/operations/strategies")
def operations_strategies(_tenant: OpsTenant, service: OpsDep) -> list[dict[str, Any]]:
    return service.strategies()


@router.get("/operations/strategies/{strategy_name}/symbols")
def operations_strategy_symbols(
    strategy_name: str,
    _tenant: OpsTenant,
    service: OpsDep,
) -> list[dict[str, Any]]:
    return service.strategy_symbols(strategy_name)


@router.get("/operations/analytics")
def operations_analytics(
    _tenant: OpsTenant,
    service: OpsDep,
    strategy: str | None = None,
) -> dict[str, Any]:
    return {
        "strategies": service.strategies(),
        "symbols": service.strategy_symbols(strategy),
        "option_metadata": "parsed_from_symbol_when_present",
    }
