from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import text

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


@router.get("/health/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(request: Request) -> ReadinessResponse:
    return await _dependency_report(request)


@router.get("/health/dependencies", response_model=ReadinessResponse)
async def dependencies(request: Request) -> ReadinessResponse:
    return await _dependency_report(request)


async def _dependency_report(request: Request) -> ReadinessResponse:
    checks: list[DependencyStatus] = []

    try:
        factory = request.app.state.session_factory
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        checks.append(DependencyStatus(name="postgres", healthy=True))
    except Exception as error:
        checks.append(DependencyStatus(name="postgres", healthy=False, detail=type(error).__name__))

    redis_ok = await request.app.state.redis.ping()
    checks.append(DependencyStatus(name="redis", healthy=redis_ok))

    status: Literal["ok", "degraded"] = "ok" if all(c.healthy for c in checks) else "degraded"
    return ReadinessResponse(status=status, dependencies=checks)
