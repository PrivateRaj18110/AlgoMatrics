"""Unit tests for the global per-IP rate-limit middleware (Phase 5, slice B)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from algo_platform.api.middleware.rate_limit import RateLimitMiddleware
from algo_platform.shared.infrastructure.rate_limiting import RateLimiter, RateLimitRule


class _InMemoryStore:
    def __init__(self) -> None:
        self._hits: dict[str, list[int]] = {}

    async def hit(self, key: str, *, window_ms: int, now_ms: int) -> int:
        bucket = self._hits.setdefault(key, [])
        bucket[:] = [t for t in bucket if t > now_ms - window_ms]
        bucket.append(now_ms)
        return len(bucket)


def _app(limit: int) -> FastAPI:
    app = FastAPI()
    app.state.rate_limiter = RateLimiter(_InMemoryStore())
    app.add_middleware(RateLimitMiddleware, rule=RateLimitRule(limit=limit, window_seconds=60))

    @app.get("/api/v1/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/health/live")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_allows_until_limit_then_429_with_headers() -> None:
    with TestClient(_app(limit=3)) as client:
        for _ in range(3):
            ok = client.get("/api/v1/ping")
            assert ok.status_code == 200
            assert ok.headers["X-RateLimit-Limit"] == "3"
        blocked = client.get("/api/v1/ping")
        assert blocked.status_code == 429
        assert blocked.headers["Retry-After"] == "60"
        assert blocked.headers["X-RateLimit-Remaining"] == "0"
        assert blocked.json()["code"] == "rate_limited"


def test_health_is_exempt() -> None:
    with TestClient(_app(limit=1)) as client:
        for _ in range(5):
            assert client.get("/api/v1/health/live").status_code == 200


def test_remaining_header_counts_down() -> None:
    with TestClient(_app(limit=5)) as client:
        first = client.get("/api/v1/ping")
        assert first.headers["X-RateLimit-Remaining"] == "4"
        second = client.get("/api/v1/ping")
        assert second.headers["X-RateLimit-Remaining"] == "3"


def test_missing_limiter_is_fail_open() -> None:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, rule=RateLimitRule(limit=1, window_seconds=60))

    @app.get("/api/v1/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(app) as client:
        for _ in range(5):
            assert client.get("/api/v1/ping").status_code == 200
