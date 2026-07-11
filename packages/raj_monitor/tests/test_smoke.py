"""Smoke tests for the Raj Monitor package.

These exercise the failure-mode guarantees without needing a running backend:
queue persistence, overflow drop-oldest, the circuit breaker, compression,
event builders, and the SDK->Agent localhost path in offline mode.

Run with pytest, or directly::

    python raj_monitor/tests/test_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import urllib.request

# Allow `python tests/test_smoke.py` from the package dir.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from raj_monitor import events  # noqa: E402
from raj_monitor.cache import Cache  # noqa: E402
from raj_monitor.compression import decode_json, encode_json  # noqa: E402
from raj_monitor.config import load_config  # noqa: E402
from raj_monitor.queue import PersistentQueue  # noqa: E402
from raj_monitor.retry import CircuitBreaker, backoff_delays  # noqa: E402
from raj_monitor.types import Envelope  # noqa: E402


def _tmp_db() -> str:
    return os.path.join(tempfile.mkdtemp(prefix="raj_test_"), "q.db")


def test_queue_overflow_drops_oldest():
    cache = Cache(_tmp_db())
    q = PersistentQueue(cache, max_size=5)
    for i in range(8):
        q.put(Envelope(kind="event", data={"i": i}, strategy="S", machine="M"))
    assert q.size() == 5
    assert q.dropped_total == 3
    first = q.peek_batch(10)[0]
    assert first.envelope.data["i"] == 3  # 0,1,2 dropped
    cache.close()


def test_queue_survives_reopen():
    db = _tmp_db()
    cache = Cache(db)
    q = PersistentQueue(cache, max_size=100)
    q.put(Envelope(kind="event", data={"x": 1}, strategy="S", machine="M"))
    q.put(Envelope(kind="trade", data={"x": 2}, strategy="S", machine="M"))
    cache.close()

    cache2 = Cache(db)  # simulate a reboot
    q2 = PersistentQueue(cache2, max_size=100)
    assert q2.size() == 2
    items = q2.peek_batch(10)
    q2.delete([it.rowid for it in items])
    assert q2.size() == 0
    cache2.close()


def test_circuit_breaker_trips_and_recovers():
    cb = CircuitBreaker(threshold=3, cooldown=0.2)
    assert cb.state() == "closed"
    for _ in range(3):
        cb.record_failure()
    assert cb.is_open is True
    assert cb.state() == "open"
    time.sleep(0.25)
    assert cb.is_open is False  # half-open after cooldown
    cb.record_success()
    assert cb.state() == "closed"


def test_backoff_delays_are_capped():
    delays = list(backoff_delays(count=10, base=0.5, cap=5.0))
    assert len(delays) == 10
    assert all(0 <= d <= 5.0 * 1.25 + 0.01 for d in delays)


def test_compression_roundtrip():
    payload = {"items": [{"k": i, "v": "x" * 50} for i in range(50)]}
    body, gz = encode_json(payload, min_bytes=100)
    assert gz is True
    assert decode_json(body, gzipped=gz) == payload
    # small payloads are left uncompressed
    small, gz2 = encode_json({"a": 1}, min_bytes=100)
    assert gz2 is False


def test_event_builders_normalise():
    tr = events.build_trade(symbol="EURUSD", direction="buy", action="open",
                            entry=1.085, quantity=1.0)
    assert tr["direction"] == "long" and tr["action"] == "open"
    ev = events.build_event("hi", severity="error")
    assert ev["severity"] == "critical"
    lg = events.build_log("x", level="warning")
    assert lg["level"] == "warn"


def test_config_defaults_without_file():
    cfg = load_config("definitely-missing.yaml")
    assert cfg.agent_port == 8765
    assert cfg.backend_url.endswith("/api")
    assert cfg.heartbeat_sec == 5


def test_sdk_to_agent_offline_holds_events():
    """SDK posts reach the agent; with the backend down they stay queued."""
    from raj_monitor.agent import Agent
    from raj_monitor.config import Config

    port = 8788
    cfg = Config(
        machine_name="SmokeMachine", agent_port=port,
        backend_url="http://127.0.0.1:59998/api",  # nothing listening
        queue_db=_tmp_db(), log_dir="", heartbeat_sec=1, metrics_sec=1, upload_sec=1,
    )
    agent = Agent(cfg)
    import threading
    threading.Thread(target=agent.run, daemon=True).start()
    try:
        time.sleep(1.0)
        health = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3).read())
        assert health["status"] == "ok"

        # Post directly to the agent (mimics the SDK).
        env = {"kind": "event", "strategy": "MR-FX", "machine": "SmokeMachine",
               "data": {"message": "hello", "category": "strategy", "severity": "info"}}
        req = urllib.request.Request(f"http://127.0.0.1:{port}/ingest",
                                     data=json.dumps(env).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=3).read()

        time.sleep(2.0)
        stats = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/stats", timeout=3).read())
        assert stats["queued"] > 0          # nothing uploaded (backend down)
        assert stats["uploaded"] == 0
        assert stats["breaker"] in ("open", "half-open", "closed")
    finally:
        agent.shutdown()


def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {exc!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
