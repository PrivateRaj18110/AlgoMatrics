# Monitor SDK Integration

> **Update (v4.0 — Raj Monitor Platform).** The monitoring infrastructure is now
> built as a dedicated package: [`raj_monitor/`](../raj_monitor/README.md). It adds a **Local Agent**
> tier between strategies and the backend, so strategies never talk to the network directly:
>
> ```
> Strategy → monitor_sdk → Local Agent → FastAPI (/api/agent/*) → Supabase → Dashboard
> ```
>
> For new deployments, follow [`raj_monitor/README.md`](../raj_monitor/README.md) and the per-OS
> install guides ([Windows](../raj_monitor/INSTALL_WINDOWS.md) · [Linux/GCloud/VPS](../raj_monitor/INSTALL_LINUX.md)).
> The reference implementation below documents the original **direct** `/api/ingest/*` path, which is
> retained for backward compatibility but superseded by the agent platform.

This was the final implementation task for Raj Quant OS. The entire platform — frontend,
backend, endpoints, websocket and docs — was already complete; what remained was the monitoring
client, now delivered as the `raj_monitor` package.

The backend exposes **every endpoint the SDK needs** under both `/api/ingest/*` (legacy direct) and
`/api/agent/*` (agent platform).

---

## 1. The target API

```python
from monitor_sdk import monitor

monitor.start()                       # announce the strategy is running
monitor.trade(symbol="EURUSD", direction="long", entry=1.0850, exit=1.0890,
              quantity=1.0, pnl=320.0)
monitor.position(symbol="EURUSD", direction="long", quantity=1.0, entry=1.0850,
                 unrealized_pnl=120.0)
monitor.metric("sharpe", 1.84)
monitor.event("Regime switched to trend", severity="info")
monitor.error("Broker timeout", traceback=tb)
monitor.heartbeat(cpu=41.2, ram=63.0)  # call periodically
```

Each method maps 1:1 to a backend endpoint:

| SDK method            | HTTP request                       | Payload schema (`app/schemas/ingest.py`) |
| --------------------- | ---------------------------------- | ---------------------------------------- |
| `monitor.start()`     | `POST /api/ingest/start`           | `StartPayload`     |
| `monitor.heartbeat()` | `POST /api/ingest/heartbeat`       | `HeartbeatPayload` |
| `monitor.trade()`     | `POST /api/ingest/trade`           | `TradePayload`     |
| `monitor.position()`  | `POST /api/ingest/position`        | `PositionPayload`  |
| `monitor.metric()`    | `POST /api/ingest/metric`          | `MetricPayload`    |
| `monitor.event()`     | `POST /api/ingest/event`           | `EventPayload`     |
| `monitor.error()`     | `POST /api/ingest/error`           | `ErrorPayload`     |

Every request carries the common identity envelope: `strategy`, `machine`, `account` (optional),
`token` (optional), `ts` (optional ISO timestamp). Every response is an `IngestAck`:
`{ "accepted": true, "received": "<iso>", "kind": "trade" }`.

---

## 2. Reference implementation

Drop this file in each trading project as `monitor_sdk.py`. It is dependency-light (`requests`),
non-blocking (a background sender thread + queue), and fails safe (network errors never crash the
strategy).

```python
"""monitor_sdk.py — Raj Quant OS strategy monitoring client.

Usage:
    from monitor_sdk import monitor
    monitor.start()
    monitor.trade(symbol="EURUSD", direction="long", entry=1.085, exit=1.089,
                  quantity=1.0, pnl=320.0)

Configure via environment variables:
    RAJ_API_BASE   default "http://localhost:8000/api"
    RAJ_STRATEGY   e.g. "MR-FX"
    RAJ_MACHINE    e.g. "London VPS"
    RAJ_ACCOUNT    e.g. "LIVE-001"   (optional)
    RAJ_TOKEN      ingest auth token (optional)
"""
from __future__ import annotations

import atexit
import os
import queue
import threading
import time
from datetime import datetime, timezone

import requests


class Monitor:
    def __init__(self) -> None:
        self.base = os.getenv("RAJ_API_BASE", "http://localhost:8000/api").rstrip("/")
        self.strategy = os.getenv("RAJ_STRATEGY", "unknown")
        self.machine = os.getenv("RAJ_MACHINE", "unknown")
        self.account = os.getenv("RAJ_ACCOUNT")
        self.token = os.getenv("RAJ_TOKEN")
        self._q: "queue.Queue[tuple[str, dict] | None]" = queue.Queue(maxsize=1000)
        self._session = requests.Session()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()
        atexit.register(self.close)

    # -- public API --------------------------------------------------------
    def start(self, **kw) -> None:
        self._send("start", kw)

    def heartbeat(self, **kw) -> None:
        self._send("heartbeat", kw)

    def trade(self, **kw) -> None:
        self._send("trade", kw)

    def position(self, **kw) -> None:
        self._send("position", kw)

    def metric(self, name: str, value: float, unit: str | None = None) -> None:
        self._send("metric", {"name": name, "value": value, "unit": unit})

    def event(self, message: str, category: str = "strategy", severity: str = "info") -> None:
        self._send("event", {"message": message, "category": category, "severity": severity})

    def error(self, message: str, traceback: str | None = None, context: dict | None = None) -> None:
        self._send("error", {"message": message, "traceback": traceback, "context": context})

    def close(self) -> None:
        self._q.put(None)

    # -- internals ---------------------------------------------------------
    def _envelope(self, body: dict) -> dict:
        return {
            "strategy": self.strategy,
            "machine": self.machine,
            "account": self.account,
            "token": self.token,
            "ts": datetime.now(timezone.utc).isoformat(),
            **{k: v for k, v in body.items() if v is not None},
        }

    def _send(self, kind: str, body: dict) -> None:
        try:
            self._q.put_nowait((kind, self._envelope(body)))
        except queue.Full:
            pass  # drop under backpressure rather than block the strategy

    def _run(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            kind, payload = item
            try:
                self._session.post(f"{self.base}/ingest/{kind}", json=payload, timeout=3)
            except Exception:
                pass  # never let monitoring break trading


monitor = Monitor()
```

---

## 3. Wiring into a strategy

```python
import traceback
from monitor_sdk import monitor

monitor.start(version="1.4.0", broker="IC Markets", symbols=["EURUSD", "GBPUSD"])

try:
    while running:
        monitor.heartbeat(cpu=read_cpu(), ram=read_ram(), open_positions=len(positions))

        signal = strategy.next()
        if signal:
            order = broker.send(signal)
            monitor.trade(
                symbol=order.symbol, direction=order.side, entry=order.price,
                exit=None, quantity=order.qty, status="open", latencyMs=order.latency_ms,
            )
except Exception:
    monitor.error("Strategy crashed", traceback=traceback.format_exc())
    raise
```

> Field names in `trade()` / `heartbeat()` match the payload schema (`latencyMs`, `durationSec`,
> `brokerPingMs`, `openPositions`). Pass them as keyword arguments.

---

## 4. Deploy to the three projects

Copy `monitor_sdk.py` into each project and set the env vars per host:

| Project              | `RAJ_MACHINE`        | `RAJ_API_BASE`                          |
| -------------------- | -------------------- | --------------------------------------- |
| London VPS Strategy  | `London VPS`         | `http://<ops-host>:8000/api`            |
| Google Cloud Strategy| `Google Cloud`       | `http://<ops-host>:8000/api`            |
| Personal PC Strategy | `Personal Computer`  | `http://<ops-host>:8000/api`            |

Point `RAJ_API_BASE` at wherever the FastAPI backend runs (and set `VITE_API_BASE_URL` +
`VITE_USE_MOCK=false` on the frontend to read live data instead of mocks).

---

## 5. Verify the integration

```bash
# 1. Start the backend
cd backend && uvicorn main:app --reload

# 2. Fire a test event (simulates monitor.event())
curl -X POST http://localhost:8000/api/ingest/event \
  -H "Content-Type: application/json" \
  -d '{"strategy":"MR-FX","machine":"London VPS","category":"strategy","severity":"info","message":"hello from SDK"}'

# 3. Confirm it landed in the event feed
curl http://localhost:8000/api/events?limit=1
```

The event also broadcasts to every connected websocket client, so an open dashboard shows it appear in
the **Event Terminal** in real time.

---

## 6. Optional hardening (later)

- **Auth:** honour the `token` field server-side (`IngestBase.token`) and reject unknown tokens.
- **Batching:** the SDK can buffer metrics and flush every N seconds to cut request volume.
- **Persistence:** once Supabase is connected, the ingest service writes to Postgres instead of the
  in-memory repositories — the SDK and endpoints stay identical.
