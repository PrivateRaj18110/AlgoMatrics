"""Raj Local Agent — one background process per machine.

Pipeline position:

    Strategy -> monitor_sdk -> [ LOCAL AGENT ] -> FastAPI -> Supabase -> Dashboard

Responsibilities:

* Expose a **localhost-only** HTTP API the SDK posts telemetry to.
* Persist everything to a **crash/reboot-safe SQLite queue** (never lose events).
* Collect host **metrics** and emit **heartbeats** on a timer.
* **Register** with the backend, then **batch-upload** queued telemetry with
  retry + circuit breaking. Offline? Keep collecting; upload when back.

Run it:

    python -m raj_monitor.agent --config config.yaml

Supported on Windows, Linux, Google Cloud and generic VPS hosts.
"""

from __future__ import annotations

import argparse
import json
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from . import constants, security
from .cache import Cache
from .config import Config, load_config
from .heartbeat import build_heartbeat
from .logger import get_logger
from .metrics import MetricsCollector
from .queue import PersistentQueue
from .transport import BackendTransport
from .types import Envelope, new_id


class Agent:
    """The long-running Local Agent process."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.log = get_logger(
            "raj_agent",
            level=cfg.log_level,
            log_dir=cfg.log_dir,
            max_bytes=cfg.log_max_bytes,
            backup_count=cfg.log_backup_count,
        )
        self.cache = Cache(cfg.queue_db)
        self.queue = PersistentQueue(self.cache, cfg.queue_max_size)
        self.agent_id = self._load_or_create_agent_id()
        self.transport = BackendTransport(cfg, self.agent_id, self.log)
        self.metrics = MetricsCollector()

        self._stop = threading.Event()
        self._strategies: set[str] = set()
        self._strategies_lock = threading.Lock()
        self._httpd: ThreadingHTTPServer | None = None
        self._threads: list[threading.Thread] = []
        self.uploaded_total = 0

    # -- lifecycle ---------------------------------------------------------
    def run(self) -> None:
        self.log.info("Raj Local Agent v%s starting (machine=%s, agent_id=%s)",
                      constants.SDK_VERSION, self.cfg.machine_name, self.agent_id)
        # Bring the local API up FIRST so the SDK can hand off immediately, then
        # register with the backend in the background (it may be slow / down).
        self._start_http_server()
        self._spawn(self._register, "register")
        self._spawn(self._metrics_loop, "metrics")
        self._spawn(self._heartbeat_loop, "heartbeat")
        self._spawn(self._upload_loop, "uploader")
        self.log.info("Agent ready. Local API on http://%s:%d  | queued=%d",
                      self.cfg.agent_host, self.cfg.agent_port, self.queue.size())
        try:
            while not self._stop.wait(1.0):
                pass
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        if self._stop.is_set() and self._httpd is None:
            return
        self.log.info("Agent shutting down...")
        self._stop.set()
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None
        # Final flush attempt so a clean stop doesn't strand the last batch.
        try:
            self._drain_once()
        except Exception:
            pass
        self.cache.close()
        self.log.info("Agent stopped. (uploaded=%d, dropped=%d)",
                      self.uploaded_total, self.queue.dropped_total)

    # -- backend registration ---------------------------------------------
    def _register(self) -> None:
        info = {
            "agentId": self.agent_id,
            "machine": self.cfg.machine_name,
            "location": self.cfg.location,
            "provider": self.cfg.provider,
            "sdkVersion": constants.SDK_VERSION,
            "python": self.metrics.python_info().get("version"),
            "os": self.metrics.snapshot().get("os"),
        }
        self.transport.register(info)

    # -- local HTTP API (SDK -> Agent) ------------------------------------
    def _start_http_server(self) -> None:
        agent = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):  # silence default stderr spam
                pass

            def _send(self, code: int, body: dict[str, Any]) -> None:
                raw = json.dumps(body).encode("utf-8")
                # The SDK opens a fresh connection per envelope (fire-and-forget),
                # so close after each response instead of holding it open. This
                # avoids a Windows keep-alive race (WinError 10053/10054) where a
                # lingering HTTP/1.1 connection is reset, dropping rapid posts such
                # as a trade's follow-up close/metric events.
                self.close_connection = True
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:  # noqa: N802
                if self.path == constants.LOCAL_HEALTH_PATH:
                    self._send(200, {"status": "ok", "agentId": agent.agent_id,
                                     "machine": agent.cfg.machine_name})
                elif self.path == constants.LOCAL_STATS_PATH:
                    self._send(200, agent.stats())
                else:
                    self._send(404, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                if self.path != constants.LOCAL_INGEST_PATH:
                    self._send(404, {"error": "not found"})
                    return
                token = self.headers.get(constants.LOCAL_TOKEN_HEADER)
                if not security.tokens_match(agent.cfg.local_token, token):
                    self._send(401, {"error": "unauthorized"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    raw = self.rfile.read(length) if length else b"{}"
                    payload = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    self._send(400, {"error": "invalid json"})
                    return
                try:
                    agent.ingest(payload)
                    self._send(202, {"accepted": True})
                except Exception as exc:  # never crash on a bad item
                    agent.log.warning("ingest error: %s", exc)
                    self._send(202, {"accepted": False})

        self._httpd = ThreadingHTTPServer((self.cfg.agent_host, self.cfg.agent_port), Handler)
        self._httpd.daemon_threads = True
        t = threading.Thread(target=self._httpd.serve_forever, name="raj-agent-http", daemon=True)
        t.start()
        self._threads.append(t)

    def ingest(self, payload: dict[str, Any]) -> None:
        """Persist one envelope from the SDK into the durable queue."""
        env = Envelope.from_dict(payload)
        if env.kind not in constants.ALL_KINDS:
            self.log.debug("dropping unknown kind: %s", env.kind)
            return
        with self._strategies_lock:
            if env.strategy and env.strategy != "unknown":
                self._strategies.add(env.strategy)
        self.queue.put(env)

    # -- background loops --------------------------------------------------
    def _metrics_loop(self) -> None:
        while not self._stop.wait(self.cfg.metrics_sec):
            try:
                snap = self.metrics.snapshot()
                self.queue.put(self._agent_envelope(constants.KIND_METRICS, snap))
            except Exception as exc:
                self.log.warning("metrics collection failed: %s", exc)

    def _heartbeat_loop(self) -> None:
        # Emit one immediately so the dashboard lights up fast, then on interval.
        while not self._stop.is_set():
            try:
                snap = self.metrics.snapshot()
                hb = build_heartbeat(
                    machine=self.cfg.machine_name,
                    agent_id=self.agent_id,
                    metrics=snap,
                    strategy_count=self._strategy_count(),
                )
                self.queue.put(self._agent_envelope(constants.KIND_HEARTBEAT, hb))
            except Exception as exc:
                self.log.warning("heartbeat failed: %s", exc)
            if self._stop.wait(self.cfg.heartbeat_sec):
                break

    def _upload_loop(self) -> None:
        while not self._stop.wait(self.cfg.upload_sec):
            try:
                self._drain_once()
            except Exception as exc:
                self.log.debug("upload cycle error: %s", exc)

    def _drain_once(self) -> None:
        """Upload as many batches as are queued, one batch per call cycle."""
        items = self.queue.peek_batch(self.cfg.batch_size)
        if not items:
            return
        payload = [it.envelope.as_dict() for it in items]
        rowids = [it.rowid for it in items]
        try:
            self.transport.upload_batch(payload)
        except Exception as exc:
            self.queue.mark_attempt(rowids)
            self.log.info("batch of %d held in queue (backend down: %s); breaker=%s, queued=%d",
                          len(rowids), exc, self.transport.breaker_state, self.queue.size())
            return
        self.queue.delete(rowids)
        self.uploaded_total += len(rowids)
        self.log.debug("uploaded %d items (remaining=%d)", len(rowids), self.queue.size())

    # -- helpers -----------------------------------------------------------
    def _agent_envelope(self, kind: str, data: dict[str, Any]) -> Envelope:
        return Envelope(kind=kind, data=data, strategy="agent",
                        machine=self.cfg.machine_name, account=None)

    def _strategy_count(self) -> int:
        with self._strategies_lock:
            return len(self._strategies)

    def _spawn(self, target, name: str) -> None:
        t = threading.Thread(target=target, name=f"raj-agent-{name}", daemon=True)
        t.start()
        self._threads.append(t)

    def _load_or_create_agent_id(self) -> str:
        existing = self.cache.get_meta("agent_id")
        if existing:
            return existing
        agent_id = new_id("agent")
        self.cache.set_meta("agent_id", agent_id)
        return agent_id

    def stats(self) -> dict[str, Any]:
        return {
            "agentId": self.agent_id,
            "machine": self.cfg.machine_name,
            "queued": self.queue.size(),
            "uploaded": self.uploaded_total,
            "dropped": self.queue.dropped_total,
            "strategies": self._strategy_count(),
            "breaker": self.transport.breaker_state,
            "backend": self.cfg.backend_url,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Raj Local Agent")
    parser.add_argument("--config", "-c", default=None, help="Path to config.yaml")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    agent = Agent(cfg)

    def _handle_signal(signum, _frame):
        agent.log.info("received signal %s", signum)
        agent.shutdown()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, OSError):  # not in main thread / unsupported
            pass

    agent.run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
