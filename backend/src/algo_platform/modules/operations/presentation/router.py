from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from algo_platform.api.dependencies.core import SettingsDep
from algo_platform.api.dependencies.tenant import TenantContext, require_permission
from algo_platform.modules.operations.application.service import OperationsService
from algo_platform.modules.operations.infrastructure.telemetry_store import TelemetryStore
from algo_platform.modules.operations.presentation.schemas import (
    OpsAnalytics,
    OpsEvent,
    OpsMachine,
    OpsOverview,
    OpsStrategyRow,
    OpsSymbolRow,
    OpsTrade,
    SystemHealthResponse,
)
from algo_platform.modules.organizations.domain.roles import Permission

router = APIRouter(tags=["operations"])

require_ops_read = require_permission(Permission.TRADING_VIEW)
OpsTenant = Annotated[TenantContext, Depends(require_ops_read)]


def get_operations_service(settings: SettingsDep) -> OperationsService:
    return OperationsService(
        TelemetryStore(settings.ops_database_url),
        app_env=settings.app_env,
    )


OpsDep = Annotated[OperationsService, Depends(get_operations_service)]


@router.get("/operations/overview", response_model=OpsOverview)
def operations_overview(_tenant: OpsTenant, service: OpsDep) -> OpsOverview:
    return OpsOverview.model_validate(service.overview())


@router.get("/operations/machines", response_model=list[OpsMachine])
def operations_machines(_tenant: OpsTenant, service: OpsDep) -> list[OpsMachine]:
    return [OpsMachine.model_validate(row) for row in service.machines()]


@router.get("/operations/events", response_model=list[OpsEvent])
def operations_events(
    _tenant: OpsTenant,
    service: OpsDep,
    limit: int = Query(200, ge=1, le=400),
    offset: int = Query(0, ge=0),
    event_type: str | None = Query(default=None),
    machine_id: str | None = Query(default=None),
    strategy: str | None = None,
    symbol: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[OpsEvent]:
    rows = service.events(
        limit=limit,
        offset=offset,
        event_type=event_type,
        machine_id=machine_id,
        strategy=strategy,
        symbol=symbol,
        since=since,
        until=until,
    )
    return [OpsEvent.model_validate(row) for row in rows]


@router.get("/operations/logs", response_model=list[OpsEvent])
def operations_logs(
    _tenant: OpsTenant,
    service: OpsDep,
    limit: int = Query(200, ge=1, le=400),
    offset: int = Query(0, ge=0),
) -> list[OpsEvent]:
    return [OpsEvent.model_validate(row) for row in service.logs(limit=limit, offset=offset)]


@router.get("/operations/alerts", response_model=list[OpsEvent])
def operations_alerts(
    _tenant: OpsTenant,
    service: OpsDep,
    limit: int = Query(200, ge=1, le=400),
    offset: int = Query(0, ge=0),
) -> list[OpsEvent]:
    return [OpsEvent.model_validate(row) for row in service.alerts(limit=limit, offset=offset)]


@router.get("/operations/orders", response_model=list[OpsEvent])
def operations_orders(
    _tenant: OpsTenant,
    service: OpsDep,
    limit: int = Query(200, ge=1, le=400),
    offset: int = Query(0, ge=0),
    machine_id: str | None = None,
    strategy: str | None = None,
    symbol: str | None = None,
) -> list[OpsEvent]:
    rows = service.orders(
        limit=limit, offset=offset, machine_id=machine_id, strategy=strategy, symbol=symbol
    )
    return [OpsEvent.model_validate(row) for row in rows]


@router.get("/operations/trades", response_model=list[OpsTrade])
def operations_trades(
    _tenant: OpsTenant,
    service: OpsDep,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    strategy: str | None = None,
    symbol: str | None = None,
    machine_id: str | None = None,
    direction: str | None = None,
    status: str | None = Query(default="closed"),
    since: str | None = None,
    until: str | None = None,
) -> list[OpsTrade]:
    rows = service.closed_trades(
        limit=limit,
        offset=offset,
        strategy=strategy,
        symbol=symbol,
        machine_id=machine_id,
        direction=direction,
        status=status,
        since=since,
        until=until,
    )
    return [OpsTrade.model_validate(row) for row in rows]


@router.get("/operations/strategies", response_model=list[OpsStrategyRow])
def operations_strategies(_tenant: OpsTenant, service: OpsDep) -> list[OpsStrategyRow]:
    return [OpsStrategyRow.model_validate(row) for row in service.strategies()]


@router.get("/operations/strategies/{strategy_name}/symbols", response_model=list[OpsSymbolRow])
def operations_strategy_symbols(
    strategy_name: str,
    _tenant: OpsTenant,
    service: OpsDep,
) -> list[OpsSymbolRow]:
    return [OpsSymbolRow.model_validate(row) for row in service.strategy_symbols(strategy_name)]


@router.get("/operations/symbols", response_model=list[OpsSymbolRow])
def operations_symbols(
    _tenant: OpsTenant,
    service: OpsDep,
    symbol: str | None = None,
) -> list[OpsSymbolRow]:
    return [OpsSymbolRow.model_validate(row) for row in service.symbol_strategies(symbol)]


@router.get("/operations/analytics", response_model=OpsAnalytics)
def operations_analytics(
    _tenant: OpsTenant,
    service: OpsDep,
    strategy: str | None = None,
) -> OpsAnalytics:
    return OpsAnalytics.model_validate(service.analytics(strategy))


@router.get("/operations/health", response_model=SystemHealthResponse)
@router.get("/operations/system-health", response_model=SystemHealthResponse)
def operations_system_health(
    _tenant: OpsTenant,
    service: OpsDep,
    machine_id: str | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int = Query(500, ge=1, le=1000),
) -> SystemHealthResponse:
    start_dt = None
    end_dt = None
    if start:
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except Exception:
            pass
    if end:
        try:
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except Exception:
            pass
    result = service.system_health(
        machine_id=machine_id,
        start=start_dt,
        end=end_dt,
        limit=limit,
    )
    return SystemHealthResponse.model_validate(result)
