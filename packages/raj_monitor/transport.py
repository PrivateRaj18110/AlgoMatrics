"""HTTP transport from the Local Agent to the FastAPI backend.

Uses the standard library only (``urllib``) so the agent has no hard HTTP
dependency. Responsibilities:

* **Batch upload** to ``/api/agent/batch`` (primary path).
* **Compression** (gzip) of large payloads.
* **Retry** with exponential backoff.
* **Timeout** on every request.
* **Circuit breaker** to stop hammering a dead backend.

Every method returns a bool / raises :class:`TransportError`; it never blocks the
caller indefinitely and never raises out of the agent's worker loop unhandled.
"""

from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from typing import Any

from . import compression, constants, security
from .config import Config
from .exceptions import CircuitOpenError, TransportError
from .retry import CircuitBreaker, backoff_delays


class BackendTransport:
    """Talks to the FastAPI backend on behalf of the agent."""

    def __init__(self, cfg: Config, agent_id: str, logger) -> None:
        self._cfg = cfg
        self._agent_id = agent_id
        self._log = logger
        self._breaker = CircuitBreaker(cfg.breaker_threshold, cfg.breaker_cooldown_sec)
        self._ssl_ctx = self._build_ssl_context(cfg)

    # -- public API --------------------------------------------------------
    def register(self, info: dict[str, Any]) -> dict[str, Any] | None:
        """Announce this agent/machine to the backend. Best-effort."""
        try:
            return self._request(constants.AGENT_REGISTER_PATH, info, retries=2)
        except TransportError as exc:
            self._log.warning("register() failed (will retry on next cycle): %s", exc)
            return None

    def upload_batch(self, items: list[dict[str, Any]]) -> bool:
        """Upload a batch of envelopes. Returns True on success."""
        if not items:
            return True
        payload = {
            "agentId": self._agent_id,
            "machine": self._cfg.machine_name,
            "count": len(items),
            "items": items,
        }
        self._request(constants.AGENT_BATCH_PATH, payload, retries=self._cfg.retry_count)
        return True

    @property
    def breaker_state(self) -> str:
        return self._breaker.state()

    # -- internals ---------------------------------------------------------
    def _request(self, path: str, payload: Any, *, retries: int) -> dict[str, Any] | None:
        url = f"{self._cfg.backend_url}{path}"
        body, gzipped = compression.encode_json(payload, min_bytes=constants.COMPRESS_MIN_BYTES)
        headers = security.backend_headers(self._cfg.backend_token, self._agent_id)
        if gzipped:
            headers["Content-Encoding"] = "gzip"

        last_exc: Exception | None = None
        # First attempt + the backoff retries.
        delays = [0.0] + list(backoff_delays(retries, self._cfg.backoff_base_sec, self._cfg.backoff_max_sec))
        for attempt, delay in enumerate(delays):
            if delay:
                import time
                time.sleep(delay)
            try:
                self._breaker.before_request()
            except CircuitOpenError as exc:
                raise TransportError(str(exc)) from exc
            try:
                result = self._do_post(url, body, headers)
                self._breaker.record_success()
                return result
            except urllib.error.HTTPError as exc:
                last_exc = exc
                # 4xx (except 429) won't fix themselves — don't retry/trip breaker.
                if 400 <= exc.code < 500 and exc.code != 429:
                    raise TransportError(f"HTTP {exc.code} from {path}: client error") from exc
                self._breaker.record_failure()
                self._log.debug("upload attempt %d -> HTTP %s", attempt + 1, exc.code)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_exc = exc
                self._breaker.record_failure()
                self._log.debug("upload attempt %d failed: %s", attempt + 1, exc)
        raise TransportError(f"All {len(delays)} attempts to {path} failed: {last_exc}")

    def _do_post(self, url: str, body: bytes, headers: dict[str, str]) -> dict[str, Any] | None:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        ctx = self._ssl_ctx if url.lower().startswith("https") else None
        with urllib.request.urlopen(req, timeout=self._cfg.timeout_sec, context=ctx) as resp:
            raw = resp.read()
            if not raw:
                return None
            try:
                import json
                return json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return None

    @staticmethod
    def _build_ssl_context(cfg: Config) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        if not cfg.verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx
