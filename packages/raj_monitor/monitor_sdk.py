"""monitor_sdk — the public client strategies import.

    from raj_monitor import monitor
    monitor.start()
    monitor.trade(symbol="EURUSD", direction="long", action="open",
                  entry=1.0850, quantity=1.0)
    monitor.stop()

Design contract (these guarantees are why it is safe to drop into live trading):

* **Non-blocking.** Every public method just enqueues onto an in-memory queue and
  returns; a daemon thread does the network I/O. The trading thread NEVER waits
  on the network.
* **Agent-only.** The SDK talks exclusively to the **Local Agent** on localhost
  (default ``http://127.0.0.1:8765``). It never uploads to the backend directly.
* **Fail-safe.** If the agent is down, items are retried from the in-memory queue;
  under sustained backpressure the oldest are dropped rather than blocking. No
  monitoring error ever propagates into the strategy.

Configure via environment variables (no code changes per host):
    RAJ_STRATEGY     e.g. "MR-FX"            (required-ish; defaults to "unknown")
    RAJ_MACHINE      e.g. "London VPS"
    RAJ_ACCOUNT      e.g. "LIVE-001"         (optional)
    RAJ_AGENT_HOST   default "127.0.0.1"
    RAJ_AGENT_PORT   default 8765
    RAJ_LOCAL_TOKEN  shared token with the agent (optional but recommended)
"""

from __future__ import annotations

import atexit
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from . import constants, events, security
from .types import Envelope

# Upper bound (seconds) stop() will wait for the in-memory queue to flush to the
# local agent before shutting the background sender down. Keeps a clean shutdown
# lossless without ever blocking the strategy indefinitely.
STOP_FLUSH_TIMEOUT_SEC = 5.0


class Monitor:
    """The strategy-facing monitoring client. Import the ``monitor`` singleton."""

    def __init__(self) -> None:
        self.strategy = os.getenv("RAJ_STRATEGY", "unknown")
        self.machine = os.getenv("RAJ_MACHINE", "unknown")
        self.account = os.getenv("RAJ_ACCOUNT") or None
        host = os.getenv("RAJ_AGENT_HOST", constants.DEFAULT_AGENT_HOST)
        port = int(os.getenv("RAJ_AGENT_PORT", str(constants.DEFAULT_AGENT_PORT)))
        self._url = f"http://{host}:{port}{constants.LOCAL_INGEST_PATH}"
        self._headers = security.local_headers(os.getenv("RAJ_LOCAL_TOKEN"))
        # The agent is always on localhost, so a proxy must never be used. Build a
        # dedicated opener with proxies disabled: the default urllib opener calls
        # getproxies() on every request, which on Windows performs WinINET/WPAD
        # registry lookups that add hundreds of ms per post and throttle bursts.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        self._q: "queue.Queue[Envelope | None]" = queue.Queue(maxsize=constants.DEFAULT_SDK_QUEUE_SIZE)
        self._started = False
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self.dropped = 0

    # -- lifecycle ---------------------------------------------------------
    def start(self, **meta: Any) -> None:
        """Announce the strategy is running and start the background sender."""
        with self._lock:
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, name="raj-monitor-sdk", daemon=True)
                self._worker.start()
                atexit.register(self.stop)
            self._started = True
        self._emit(constants.KIND_START, {
            "version": meta.get("version"),
            "broker": meta.get("broker"),
            "symbols": meta.get("symbols", []),
            "message": "Strategy started",
        })

    def stop(self) -> None:
        """Flush a final 'stopped' event, drain the queue, and shut the worker down."""
        if not self._started:
            return
        self._emit(constants.KIND_STOP, {"message": "Strategy stopped"})
        self._started = False
        # Give the background sender a bounded chance to flush everything still
        # queued. A burst of trades immediately before stop() would otherwise be
        # stranded behind the shutdown sentinel. Bounded, so a clean shutdown is
        # never blocked for long if the agent happens to be unreachable.
        deadline = time.monotonic() + STOP_FLUSH_TIMEOUT_SEC
        while self._q.qsize() > 0 and time.monotonic() < deadline:
            time.sleep(0.02)
        try:
            self._q.put_nowait(None)  # sentinel: drain remaining, then exit
        except queue.Full:
            pass
        worker = self._worker
        if worker is not None:
            worker.join(timeout=2.0)

    # -- public telemetry API (stable forever) -----------------------------
    def trade(self, **kw: Any) -> None:
        """Record a trade lifecycle event (open/close/modify/pending/cancelled/rejected)."""
        self._emit(constants.KIND_TRADE, events.build_trade(**kw))

    def position(self, **kw: Any) -> None:
        """Snapshot an open position."""
        self._emit(constants.KIND_POSITION, events.build_position(**kw))

    def metric(self, name: str, value: float, unit: str | None = None) -> None:
        """Report a named numeric metric (e.g. sharpe, slippage)."""
        self._emit(constants.KIND_METRIC, events.build_metric(name, value, unit))

    def event(self, message: str, category: str = "strategy", severity: str = "info") -> None:
        """Emit a domain event for the live terminal."""
        self._emit(constants.KIND_EVENT, events.build_event(message, category, severity))

    def error(self, message: str, traceback: str | None = None, context: dict | None = None) -> None:
        """Report an exception / error (surfaces as a critical event)."""
        self._emit(constants.KIND_ERROR, events.build_error(message, traceback, context))

    def log(self, message: str, level: str = "info", logger: str = "strategy") -> None:
        """Send a structured log line."""
        self._emit(constants.KIND_LOG, events.build_log(message, level, logger))

    def heartbeat(self, **kw: Any) -> None:
        """Optional manual heartbeat (the Agent also sends host heartbeats)."""
        self._emit(constants.KIND_HEARTBEAT, {k: v for k, v in kw.items() if v is not None})

    # -- internals ---------------------------------------------------------
    def _emit(self, kind: str, data: dict[str, Any]) -> None:
        if self._worker is None:
            # Allow fire-and-forget before an explicit start() by auto-starting.
            with self._lock:
                if self._worker is None:
                    self._worker = threading.Thread(target=self._run, name="raj-monitor-sdk", daemon=True)
                    self._worker.start()
                    atexit.register(self.stop)
                    self._started = True
        env = Envelope(kind=kind, data=data, strategy=self.strategy,
                       machine=self.machine, account=self.account)
        try:
            self._q.put_nowait(env)
        except queue.Full:
            # Drop the oldest to make room — newest telemetry is most useful.
            try:
                self._q.get_nowait()
                self.dropped += 1
                self._q.put_nowait(env)
            except (queue.Empty, queue.Full):
                self.dropped += 1

    def _run(self) -> None:
        stopping = False
        while True:
            try:
                env = self._q.get(timeout=0.2)
            except queue.Empty:
                if stopping:
                    return
                continue
            if env is None:
                # Sentinel: finish draining whatever is still queued (including
                # any items re-queued after a failed post) before exiting.
                stopping = True
                continue
            self._post(env)

    def _post(self, env: Envelope) -> None:
        """POST one envelope to the local agent. Never raises."""
        try:
            body = json.dumps(env.as_dict(), default=str).encode("utf-8")
            req = urllib.request.Request(self._url, data=body, headers=self._headers, method="POST")
            with self._opener.open(req, timeout=2) as resp:
                resp.read()
        except (urllib.error.URLError, OSError, ValueError):
            # Agent unreachable: re-queue once so it isn't lost if the agent is
            # just restarting, but never block. Drop on overflow.
            try:
                self._q.put_nowait(env)
            except queue.Full:
                self.dropped += 1
            # Brief sleep so we don't spin at 100% CPU while the agent is down.
            time.sleep(0.5)


# The singleton every strategy imports.
monitor = Monitor()
