from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from algo_platform.shared.application.readiness import ProbeResult, overall_status

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


class DependencyStatus(BaseModel):
    name: str
    healthy: bool
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded"]
    dependencies: list[DependencyStatus]


class InfoResponse(BaseModel):
    service: str
    version: str
    build_sha: str
    environment: str


@router.get("/health/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/info", response_model=InfoResponse)
async def info(request: Request) -> InfoResponse:
    """Non-sensitive release identity for deploy verification / support."""
    settings = request.app.state.settings
    return InfoResponse(
        service=settings.service_name,
        version=settings.app_version,
        build_sha=settings.build_sha,
        environment=settings.app_env,
    )


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(request: Request, response: Response) -> ReadinessResponse:
    report = await _dependency_report(request)
    # Signal to the load balancer / orchestrator to route away when degraded so
    # a sick replica is taken out of rotation instead of serving traffic.
    if report.status == "degraded":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return report


@router.get("/health/dependencies", response_model=ReadinessResponse)
async def dependencies(request: Request) -> ReadinessResponse:
    # Informational: always 200 so operators can inspect component health even
    # while the readiness probe is failing.
    return await _dependency_report(request)


async def _dependency_report(request: Request) -> ReadinessResponse:
    timeout = float(getattr(request.app.state.settings, "readiness_timeout_seconds", 2.0))
    results = [
        await _probe("postgres", _check_postgres(request), timeout),
        await _probe("redis", _check_redis(request), timeout),
    ]
    status_value = overall_status(results)
    return ReadinessResponse(
        status="ok" if status_value == "ok" else "degraded",
        dependencies=[
            DependencyStatus(name=r.name, healthy=r.healthy, detail=r.detail) for r in results
        ],
    )


async def _probe(name: str, coro: Awaitable[None], timeout_seconds: float) -> ProbeResult:
    try:
        async with asyncio.timeout(timeout_seconds):
            await coro
    except TimeoutError:
        return ProbeResult(name=name, healthy=False, detail="timeout")
    except Exception as error:
        return ProbeResult(name=name, healthy=False, detail=type(error).__name__)
    return ProbeResult(name=name, healthy=True)


async def _check_postgres(request: Request) -> None:
    factory = request.app.state.session_factory
    async with factory() as session:
        await session.execute(text("SELECT 1"))


async def _check_redis(request: Request) -> None:
    if not await request.app.state.redis.ping():
        raise RuntimeError("redis ping returned false")
