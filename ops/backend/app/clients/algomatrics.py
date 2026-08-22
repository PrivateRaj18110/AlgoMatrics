"""HTTP client for the AlgoMatrics control plane (``/api/v1``).

The ops dashboard reads live platform data (strategies, trades, risk,
analytics, brokers, accounts) from AlgoMatrics using an **organization-scoped
API key** (``X-API-Key`` + ``X-Org-Id`` headers, ``read`` scope). The client is
disabled unless all three ``ALGOMATRICS_*`` settings are present, in which case
the service layer falls back to the bundled mock fixtures.

A small TTL cache keeps the dashboard's polling intervals from hammering the
control plane: every page refresh collapses into at most one upstream request
per endpoint per TTL window.
"""

from __future__ import annotations

import threading
import time
from functools import lru_cache
from typing import Any

import httpx

from app.core.config import get_settings


class AlgoMatricsUnavailable(Exception):
    """Raised when the control plane cannot be reached or rejects the request."""


class AlgoMatricsClient:
    """Thin synchronous JSON client with a per-endpoint TTL cache."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        org_id: str,
        *,
        timeout_seconds: float = 5.0,
        cache_ttl_seconds: float = 5.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-API-Key": api_key, "X-Org-Id": org_id}
        self._timeout = timeout_seconds
        self._ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET ``path`` (relative to the API base) and return the parsed JSON body."""
        key = f"{path}?{sorted((params or {}).items())!r}"
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None and now - hit[0] < self._ttl:
                return hit[1]
        try:
            response = httpx.get(
                f"{self._base_url}/{path.lstrip('/')}",
                params=params,
                headers=self._headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:  # connection, timeout, or non-2xx
            raise AlgoMatricsUnavailable(str(exc)) from exc
        payload = response.json()
        with self._lock:
            self._cache[key] = (time.monotonic(), payload)
        return payload


@lru_cache
def get_algomatrics_client() -> AlgoMatricsClient | None:
    """Return the configured client, or ``None`` when live mode is disabled."""
    settings = get_settings()
    if not (
        settings.algomatrics_api_url
        and settings.algomatrics_api_key
        and settings.algomatrics_org_id
    ):
        return None
    return AlgoMatricsClient(
        settings.algomatrics_api_url,
        settings.algomatrics_api_key,
        settings.algomatrics_org_id,
        timeout_seconds=settings.algomatrics_timeout_seconds,
        cache_ttl_seconds=settings.algomatrics_cache_ttl_seconds,
    )
