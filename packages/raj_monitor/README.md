# Raj Monitor Platform

Safe, production-grade monitoring for live trading strategies — the final piece
of **Raj Quant OS v4.0**. Strategies report through a tiny, fail-safe SDK to a
**Local Agent** running on each machine; the agent durably queues telemetry and
forwards it to the FastAPI backend, which the existing dashboard already renders.

```
Strategy ──▶ monitor_sdk ──▶ Local Agent ──▶ FastAPI ──▶ Supabase ──▶ Dashboard
  (your code)   (no deps)     (per machine)   (backend)    (later)     (live UI)
```

**Why an agent in the middle?** Strategies must never block on, or be crashed by,
monitoring. The SDK only ever talks to `127.0.0.1` and returns instantly; the
agent owns the network, the retries, the persistence and the host metrics. If the
backend (or the whole internet) goes away, strategies keep trading and the agent
keeps queuing — nothing is lost.

---

## What's in the box

| File | Role |
| --- | --- |
| `monitor_sdk.py` | The `monitor` singleton strategies import. Non-blocking, stdlib-only. |
| `agent.py` | The Local Agent: localhost API + queue + metrics + heartbeat + uploader. |
| `transport.py` | Agent→backend HTTP: batching, gzip, retry, timeout, circuit breaker. |
| `queue.py` / `cache.py` | Crash/reboot-safe SQLite queue (no Redis, no external deps). |
| `metrics.py` | CPU/RAM/disk/network/internet/latency/Python/MT5/process collection. |
| `heartbeat.py` | Heartbeat payloads (every 5s by default). |
| `events.py` | Trade/event/log/metric payload builders + normalisation. |
| `config.py` / `config.yaml` | One-file configuration (YAML, env-overridable). |
| `retry.py` | Backoff + circuit breaker. |
| `compression.py` | gzip helpers. `security.py` | token auth. `logger.py` | rotating logs. |
| `constants.py` / `types.py` / `exceptions.py` | Shared protocol, dataclasses, errors. |
| `service/` | systemd unit, Windows `.bat` launcher. |
| `examples/` | Strategy integration example. |

---

## The public SDK API (stable forever)

```python
from raj_monitor import monitor

monitor.start(version="1.4.0", broker="IC Markets", symbols=["EURUSD"])
monitor.trade(symbol="EURUSD", direction="long", action="open",
              entry=1.0850, quantity=1.0)            # open/close/modify/pending/cancelled/rejected
monitor.position(symbol="EURUSD", direction="long", quantity=1.0,
                 entry=1.0850, unrealized_pnl=120.0)
monitor.metric("sharpe", 1.84)
monitor.event("Regime switched to trend", severity="info")   # info/warning/critical
monitor.error("Broker timeout", traceback=tb)
monitor.log("order book thin", level="warn")
monitor.heartbeat(cpu=41.2, ram=63.0)               # optional; agent also auto-heartbeats
monitor.stop()
```

Every call enqueues and returns immediately. Configure identity with environment
variables — **no code changes per host**:

| Variable | Meaning | Default |
| --- | --- | --- |
| `RAJ_STRATEGY` | Strategy code, e.g. `MR-FX` | `unknown` |
| `RAJ_MACHINE` | Host name (must match the agent's `machine.name`) | `unknown` |
| `RAJ_ACCOUNT` | Account label (optional) | — |
| `RAJ_AGENT_HOST` / `RAJ_AGENT_PORT` | Where the Local Agent listens | `127.0.0.1` / `8765` |
| `RAJ_LOCAL_TOKEN` | Shared secret with the agent | — |

---

## Quick start (local)

```bash
# 1) Start the backend (from the repo root)
cd backend && uvicorn main:app --reload          # http://localhost:8000

# 2) Start a Local Agent (new terminal, repo root)
cp raj_monitor/config.yaml config.yaml            # edit machine.name, backend.url
pip install psutil PyYAML                          # optional but recommended
python -m raj_monitor.agent --config config.yaml  # http://127.0.0.1:8765

# 3) Run a strategy that reports in
RAJ_STRATEGY=MR-FX RAJ_MACHINE="London VPS" \
  python raj_monitor/examples/strategy_integration.py
```

Open the dashboard with `VITE_USE_MOCK=false` and watch the machine, trades and
events appear live.

---

## Installing into the three trading projects

The package is self-contained. Two options:

1. **Copy** the `raj_monitor/` folder into the project, or
2. **Install** it: `pip install ./raj_monitor` (adds the `raj-agent` command).

Then, in the strategy, add `from raj_monitor import monitor`, call
`monitor.start()`, and replace your execution callbacks with `monitor.trade()` /
`monitor.position()` / `monitor.metric()`. Nothing else changes.

Per-host configuration:

| Project | `RAJ_MACHINE` / `machine.name` | `backend.url` |
| --- | --- | --- |
| London VPS Strategy | `London VPS` | `https://<ops-host>/api` |
| Google Cloud Strategy | `Google Cloud` | `https://<ops-host>/api` |
| Personal PC Strategy | `Personal Computer` | `https://<ops-host>/api` |

Install the agent as a service per OS:

- **Windows** → [`INSTALL_WINDOWS.md`](INSTALL_WINDOWS.md) (NSSM or Task Scheduler)
- **Linux / Google Cloud / VPS** → [`INSTALL_LINUX.md`](INSTALL_LINUX.md) (systemd)

---

## Backend endpoints (already implemented)

The agent posts to these (added in this milestone, alongside the legacy
`/api/ingest/*`):

| Endpoint | Purpose |
| --- | --- |
| `POST /api/agent/register` | Announce an agent + create its machine record |
| `POST /api/agent/heartbeat` | Liveness + host telemetry (updates the machine) |
| `POST /api/agent/metrics` | Full metrics snapshot |
| `POST /api/agent/events` | Domain events → live terminal |
| `POST /api/agent/trades` | Trade lifecycle events |
| `POST /api/agent/logs` | Structured log lines |
| `POST /api/agent/batch` | **Primary path** — a gzip batch of mixed envelopes |

The backend folds these into the same in-memory repositories + websocket feed the
dashboard already consumes, so **no UI changes were needed** — the live agent
simply replaces the mock engine for any machine that registers.

---

## Reliability & performance

- **Never blocks trading** — SDK calls are queue-and-return; all I/O is on
  background threads.
- **Never loses events** — the agent's SQLite queue survives crashes and reboots;
  uploads are deleted only after a confirmed batch.
- **Offline-tolerant** — a dead backend trips a circuit breaker; telemetry keeps
  queuing and flushes when connectivity returns.
- **Light** — SDK has zero dependencies; the agent targets <1% CPU and <100 MB RAM
  (tune `intervals.*` and `queue.batch_size`).
- **Secure** — shared token between SDK↔agent (localhost), bearer token over HTTPS
  agent↔backend.

See [`docs/AGENT.md`](docs/AGENT.md) for internals and the testing matrix.
