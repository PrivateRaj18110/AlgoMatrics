# Deploying ONE VPS to RAJ QUANT OS

**Audience:** the operator standing up a single production-like trading host (a
"VPS" — London/Beeks, a GCE instance, or a Windows trading box) so that a live
strategy on that host streams telemetry into the existing Operations Center and
appears correctly on the dashboard.

This guide deploys the pipeline **exactly as implemented** — no architecture
changes:

```
Trading Strategy ─▶ monitor SDK ─▶ Local Agent ─▶ FastAPI Backend ─▶ WebSocket ─▶ React Dashboard
   (your code)      (raj_monitor)   (127.0.0.1:8765)   (/api/agent/*)    (/api/ws)     (live UI)
```

Two trust boundaries and two hops to remember:

| Hop | Transport | Auth | Notes |
| --- | --- | --- | --- |
| Strategy → Agent | HTTP to `127.0.0.1:8765` | `X-Raj-Local-Token` (shared local token) | Never leaves the box. |
| Agent → Backend | HTTPS to `…/api/agent/*` | `X-Raj-Agent-Token` (sent; see §7 security note) | The only traffic that crosses the network. Batched + gzipped. |

> The strategy **never** talks to the backend directly. It only ever posts to the
> Local Agent on localhost. The agent owns the network, retries and durable queue.

Everything below has been validated end-to-end against this repo's backend (real
agent, real strategy, real heartbeats/trades, a backend-outage drill, and the
live websocket frames the dashboard consumes).

---

## 0. Prerequisites & inventory

Per VPS you need:

- **Python 3.10+** on the VPS (validated on 3.14).
- The `raj_monitor/` package copied to the VPS (or `pip install ./raj_monitor`).
- Network egress from the VPS to the backend host on the backend's port (443 if
  behind TLS).
- Three decisions written down before you start:

| Item | Example | Used by |
| --- | --- | --- |
| **Machine name** (unique) | `London VPS` | `machine.name` / `RAJ_STRATEGY`'s `RAJ_MACHINE` |
| **Backend URL** (include `/api`) | `https://ops.example.com/api` | `backend.url` |
| **Backend token** | a 32-byte random string | `backend.token` |
| **Local token** | a 32-byte random string | `agent.local_token` + strategy's `RAJ_LOCAL_TOKEN` |

Generate strong tokens (run anywhere with Python):

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 1. Backend configuration

The backend already implements the `/api/agent/*` tier and the `/api/ws`
websocket. You only configure environment, not code.

`backend/.env` (copy from `backend/.env.example`):

```ini
APP_NAME="Raj Quant OS API"
ENVIRONMENT=production
DEBUG=false
API_PREFIX=/api

# MUST include every browser origin that will load the dashboard.
# The agent→backend hop is server-to-server and needs NO CORS entry.
CORS_ORIGINS=https://dashboard.example.com,http://localhost:5173
```

Run it bound to all interfaces (or to localhost behind a reverse proxy):

```bash
cd backend
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000        # add --workers N behind a proxy
```

Confirm it serves:

```bash
curl http://<backend-host>:8000/api/health
# {"status":"ok","version":"1.0.0","time":"…","environment":"production"}
```

The agent endpoints the backend exposes (already wired in `app/api/router.py`):

| Endpoint | Purpose |
| --- | --- |
| `POST /api/agent/register` | Announce an agent → creates/updates its machine record |
| `POST /api/agent/heartbeat` | Liveness + host telemetry |
| `POST /api/agent/metrics` | Full metrics snapshot |
| `POST /api/agent/events` / `trades` / `logs` | Domain telemetry → live feeds |
| `POST /api/agent/batch` | **Primary path** — a gzip batch of mixed envelopes |
| `GET  /api/ws` | Websocket the dashboard subscribes to |

> **Production tip:** put the backend behind a TLS reverse proxy (nginx/Caddy)
> terminating `https://ops.example.com` → `127.0.0.1:8000`. Then the agent uses
> `backend.url: https://ops.example.com/api` with `verify_ssl: true`.

---

## 2. VPS preparation

```bash
# Linux / GCE
sudo apt-get update && sudo apt-get install -y python3 python3-venv
sudo mkdir -p /opt/raj-monitor && sudo chown "$USER" /opt/raj-monitor
# …copy the raj_monitor/ package into /opt/raj-monitor/raj_monitor …
cd /opt/raj-monitor
python3 -m venv .venv
.venv/bin/pip install psutil PyYAML
```

```powershell
# Windows VPS
mkdir C:\raj-monitor
# …copy raj_monitor\ into C:\raj-monitor\raj_monitor …
cd C:\raj-monitor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install psutil PyYAML
```

> The **SDK** needs no dependencies. `psutil` + `PyYAML` only enrich the **agent**
> (full CPU/RAM/disk metrics and richer config parsing). Without `psutil` the
> agent still runs; metrics are sparser. Without `PyYAML` a built-in mini-parser
> reads the simple `config.yaml` we ship.

---

## 3. Local Agent installation

Place the package and create the working directory that will hold the config,
the durable queue DB and the logs (one per host):

```
/opt/raj-monitor/          (Linux)            C:\raj-monitor\          (Windows)
├── raj_monitor/           ← the package      ├── raj_monitor\
├── .venv/                                     ├── .venv\
├── config.yaml            ← you create        ├── config.yaml
├── raj_agent_queue.db     ← auto, durable     ├── raj_agent_queue.db
└── logs/                  ← auto, rotating     └── logs\
```

Run the agent in the foreground once to confirm it boots (see §10).

---

## 4. monitor SDK configuration

The SDK reads its identity from **environment variables** — no per-host code
changes. The strategy process must export these (same box as the agent):

| Variable | Meaning | Required |
| --- | --- | --- |
| `RAJ_STRATEGY` | Strategy code, e.g. `MR-FX` | yes (defaults `unknown`) |
| `RAJ_MACHINE` | Host name — **must equal** the agent's `machine.name` | yes |
| `RAJ_LOCAL_TOKEN` | Shared secret — **must equal** the agent's `agent.local_token` | yes (prod) |
| `RAJ_ACCOUNT` | Account label | optional |
| `RAJ_AGENT_HOST` / `RAJ_AGENT_PORT` | Where the agent listens | default `127.0.0.1` / `8765` |

The SDK is the stable, public surface (`from raj_monitor import monitor`):

```python
monitor.start(version="1.4.0", broker="IC Markets", symbols=["EURUSD"])
monitor.trade(symbol="EURUSD", direction="long", action="open", entry=1.0850, quantity=1.0)
monitor.trade(symbol="EURUSD", direction="long", action="close", entry=1.0850, exit=1.0875, quantity=1.0, pnl=250.0)
monitor.position(symbol="EURUSD", direction="long", quantity=1.0, entry=1.0850, unrealized_pnl=120.0)
monitor.metric("sharpe", 1.84)
monitor.event("Regime switched to trend", severity="info")     # info|warning|critical
monitor.error("Broker timeout", traceback=tb)
monitor.log("order book thin", level="warn")                   # debug|info|warn|error
monitor.stop()
```

Every call enqueues and returns instantly; a daemon thread does the I/O. No
monitoring call can block or crash the trading loop.

---

## 5. Strategy integration

Minimal change to an existing strategy:

1. Copy `raj_monitor/` into the strategy project **or** `pip install ./raj_monitor`.
2. `from raj_monitor import monitor`.
3. Call `monitor.start(...)` at startup, `monitor.stop()` on shutdown (a `finally`
   block is ideal — `stop()` flushes the queue before exit).
4. Replace your execution callbacks with `monitor.trade()` / `monitor.position()`
   and add `monitor.metric()` / `monitor.event()` where useful.

`raj_monitor/examples/strategy_integration.py` is a complete, runnable template —
copy its structure verbatim. Run it as a smoke test of your wiring:

```bash
RAJ_STRATEGY=MR-FX RAJ_MACHINE="London VPS" RAJ_LOCAL_TOKEN=<local-token> \
  python raj_monitor/examples/strategy_integration.py
```

---

## 6. Environment variables (complete reference)

**Agent** (`config.yaml` keys, each env-overridable — handy for systemd/containers):

| Env | config.yaml key | Default |
| --- | --- | --- |
| `RAJ_BACKEND_URL` | `backend.url` | `http://127.0.0.1:8000/api` |
| `RAJ_BACKEND_TOKEN` | `backend.token` | — |
| `RAJ_MACHINE` | `machine.name` | `unknown` |
| `RAJ_AGENT_HOST` / `RAJ_AGENT_PORT` | `agent.host` / `agent.port` | `127.0.0.1` / `8765` |
| `RAJ_LOCAL_TOKEN` | `agent.local_token` | — |
| `RAJ_CONFIG` | (path to the config file) | `config.yaml` |

**Strategy:** `RAJ_STRATEGY`, `RAJ_MACHINE`, `RAJ_LOCAL_TOKEN` (+ optional
`RAJ_ACCOUNT`, `RAJ_AGENT_HOST/PORT`). See §4.

**Backend** (`backend/.env`): `CORS_ORIGINS`, `ENVIRONMENT`, `DEBUG`, `API_PREFIX`.

**Frontend** (`frontend/.env.local`): `VITE_API_BASE_URL`, `VITE_USE_MOCK`. See §13.

Filled `config.yaml` for the VPS:

```yaml
backend:
  url: "https://ops.example.com/api"     # include /api ; https in production
  token: "<backend-token>"
  verify_ssl: true                        # false ONLY for self-signed dev backends
  timeout_sec: 10
machine:
  name: "London VPS"                      # unique; strategies set RAJ_MACHINE to this
  location: "London · Equinix LD4"
  provider: "Beeks Financial Cloud"
agent:
  host: "127.0.0.1"                       # keep localhost — never expose 8765
  port: 8765
  local_token: "<local-token>"
intervals:
  heartbeat_sec: 5                        # dashboard flips a host offline after ~20s silent
  metrics_sec: 10
  upload_sec: 3
queue:
  max_size: 100000                        # durable on-disk; oldest dropped on overflow
  batch_size: 200
  db_path: "raj_agent_queue.db"
retry:
  count: 5
  backoff_base_sec: 0.5
  backoff_max_sec: 30
  breaker_threshold: 5                    # open the circuit after 5 consecutive failures
  breaker_cooldown_sec: 30
logging:
  level: "INFO"
  dir: "logs"
  max_bytes: 10485760
  backup_count: 5
```

---

## 7. Firewall requirements

| Direction | Port | Rule | Why |
| --- | --- | --- | --- |
| VPS **outbound** → backend | 443 (or 8000) | **Allow** | The only required connectivity: agent → `…/api/agent/*`. |
| VPS **inbound** → `8765` | 8765 | **Deny from network** | The agent's local API is for localhost strategies only. Keep it on `127.0.0.1`; never open 8765 to the network. |
| Backend host **inbound** | 443/8000 | Allow only from VPS IPs / proxy | See the security note below. |

Linux (UFW) on the VPS:

```bash
sudo ufw default deny incoming
sudo ufw allow out 443/tcp           # agent → backend (TLS)
sudo ufw allow 22/tcp                # your SSH
sudo ufw enable
# 8765 is bound to 127.0.0.1 by config; no inbound rule needed.
```

Windows VPS — block inbound 8765 from the network (it should never be remote):

```powershell
New-NetFirewallRule -DisplayName "Raj Agent localhost only" -Direction Inbound `
  -LocalPort 8765 -Protocol TCP -Action Block -RemoteAddress Internet
```

GCE: the agent only needs **egress** (default-allowed). Do not add an ingress
rule for 8765.

> **⚠ Security note (verified in this codebase):** the backend currently does
> **not enforce** `X-Raj-Agent-Token` on `/api/agent/*` — the agent sends it, but
> there is no server-side auth dependency yet. Until that is added, the network is
> your security boundary: **do not expose the backend publicly.** Put it behind a
> reverse proxy that allowlists the VPS source IPs (or a VPN/private network), and
> still set a real `backend.token` so you are ready when enforcement lands. The
> SDK↔agent hop *is* protected by `agent.local_token` because it stays on
> localhost.

---

## 8. Service installation (Windows / Linux)

Run **one** agent per host as a supervised service so it restarts on crash/reboot.
Its on-disk SQLite queue means **no telemetry is lost** across restarts.

### Linux / GCE — systemd

Use the shipped unit `raj_monitor/service/raj-agent.service` (edit paths/User):

```bash
sudo useradd --system --home /opt/raj-monitor --shell /usr/sbin/nologin raj || true
sudo chown -R raj:raj /opt/raj-monitor
sudo cp raj_monitor/service/raj-agent.service /etc/systemd/system/raj-agent.service
sudo systemctl daemon-reload
sudo systemctl enable --now raj-agent
systemctl status raj-agent
journalctl -u raj-agent -f
```

The unit sets `Restart=always` / `RestartSec=5` and starts after
`network-online.target`. You can keep identity in `config.yaml` or move it to
`Environment=` lines in the unit.

### Windows VPS — NSSM (recommended) or Task Scheduler

```powershell
# NSSM (https://nssm.cc) on PATH:
nssm install RajLocalAgent "C:\raj-monitor\raj_monitor\service\raj-agent.bat"
nssm set RajLocalAgent AppDirectory "C:\raj-monitor"
nssm set RajLocalAgent Start SERVICE_AUTO_START
nssm set RajLocalAgent AppStdout "C:\raj-monitor\logs\service.out.log"
nssm set RajLocalAgent AppStderr "C:\raj-monitor\logs\service.err.log"
nssm start RajLocalAgent
nssm status RajLocalAgent
```

Alternative without NSSM: Task Scheduler → Basic Task → Trigger *At startup* →
Action *Start a program* → `C:\raj-monitor\raj_monitor\service\raj-agent.bat`,
tick *Run whether user is logged on or not*.

(Full per-OS detail: [`INSTALL_LINUX.md`](INSTALL_LINUX.md) /
[`INSTALL_WINDOWS.md`](INSTALL_WINDOWS.md).)

---

## 9. Health verification

```bash
curl http://127.0.0.1:8765/health
# {"status":"ok","agentId":"agent-…","machine":"London VPS"}

curl http://127.0.0.1:8765/stats
# {"agentId":"…","machine":"London VPS","queued":0,"uploaded":N,"dropped":0,
#  "strategies":0,"breaker":"closed","backend":"https://ops.example.com/api"}
```

Pass criteria: `/health` returns `ok` with your machine name; `/stats` shows
`breaker: closed` (the agent reached the backend) and `dropped: 0`.

Backend reachability from the VPS:

```bash
curl https://ops.example.com/api/health      # expect {"status":"ok",…}
```

---

## 10. Heartbeat verification

The agent emits a heartbeat every `heartbeat_sec` (5s) carrying real host
telemetry. Confirm the machine appears on the backend and is being refreshed:

```bash
curl https://ops.example.com/api/machines | python -m json.tool
```

Look for a record whose **id is `mch-agent-<your-machine-slug>`** (e.g.
`mch-agent-london-vps`) with `status: "online"`, non-zero `ram`/`disk`, and a
`lastHeartbeat` that advances each time you re-query.

```jsonc
{ "id": "mch-agent-london-vps", "name": "London VPS", "status": "online",
  "cpu": 12.4, "ram": 61.0, "disk": 47.0, "strategyCount": 0,
  "lastHeartbeat": "2026-…Z" }
```

Notes that bite people:
- **First CPU reading is `0.0`** — `psutil.cpu_percent` needs one interval to warm
  up; it populates on the next snapshot. RAM/disk are correct immediately.
- The dashboard flips a live host to **offline ~20s** after the last heartbeat
  (`publisher._LIVE_STALE_AFTER_SEC`). Steady 5s heartbeats keep it online.
- **`status` reflects real health:** sustained CPU/RAM ≥ ~85–95% shows `degraded`
  /`critical` — that is the agent reporting the truth, not a bug.

---

## 11. Trade verification

Send a deterministic open+close from the host (matches what a strategy does):

```bash
RAJ_STRATEGY=MR-FX RAJ_MACHINE="London VPS" RAJ_LOCAL_TOKEN=<local-token> \
python - <<'PY'
from raj_monitor import monitor
monitor.start(version="1.0", broker="IC Markets", symbols=["EURUSD"])
monitor.trade(symbol="EURUSD", direction="long", action="open",  entry=1.0850, quantity=1.0)
monitor.trade(symbol="EURUSD", direction="long", action="close", entry=1.0850, exit=1.0875, quantity=1.0, pnl=250.0)
monitor.stop()           # flushes the queue before exit
PY
```

Then confirm both events landed (source is `"<machine> · <strategy>"`):

```bash
curl https://ops.example.com/api/events | python -m json.tool | grep -A2 "London VPS · MR-FX"
# … "Trade open LONG EURUSD · PnL +0"
# … "Trade close LONG EURUSD · PnL +250"
```

Pass criteria: **every** emitted trade appears (open *and* close), and the agent's
`/stats` shows `dropped: 0`. (Validated here under a burst of 20 rapid
open/close pairs with an immediate `stop()` — all 20 delivered, 0 dropped.)

---

## 12. Metrics verification

Custom metrics and host metrics both flow:

```bash
# strategy metric() lines surface in the logs feed:
curl https://ops.example.com/api/logs | python -m json.tool | grep "metric()"
# … "metric() sharpe=1.84"

# host metrics (CPU/RAM/disk/latency) update the machine record (see §10) and
# the full snapshot rides the /api/agent/metrics + heartbeat path every 10s.
```

Pass criteria: `metric()` lines appear in `/api/logs`, and the machine's
`cpu`/`ram`/`disk`/`internetMs` in `/api/machines` move over time.

---

## 13. Dashboard verification

Point the dashboard at the backend and turn off mock mode.

`frontend/.env.local` (copy from `frontend/.env.example`):

```ini
# Include /api — both REST (…/api/...) and the websocket (…/api/ws) derive from this.
VITE_API_BASE_URL=https://ops.example.com/api
VITE_USE_MOCK=false
```

```bash
cd frontend
npm install
npm run build && npm run preview        # or: npm run dev
```

In the browser:
1. Open **Monitoring / Machines** — your host appears as a live card (the
   `mch-agent-<slug>` record) with live CPU/RAM/disk and an advancing heartbeat.
2. Open the **live events terminal** — `Strategy started`, `Trade open/close …`,
   and your `monitor.event(...)` messages stream in from `"<machine> · <strategy>"`.
3. Confirm updates arrive **without refreshing** — that is the websocket.

**Validated:** subscribing to `wss://ops.example.com/api/ws` (exactly what the
dashboard does) delivered live `machines` frames for the live host and `event`
frames for each emitted trade in real time.

> **Expected quirk:** the bundled mock fixtures seed demo machines (some may share
> a friendly name like "London VPS"). Your **live** host is the separate card with
> id `mch-agent-<slug>`. The mock publisher never overwrites live hosts — it skips
> any machine the agent has registered. Treat the seeded demo cards as
> placeholders.

---

## 14. Failure simulation

Run these three drills before declaring the VPS production-ready. All three were
exercised against this codebase and passed with **zero telemetry loss**.

### a) Backend outage (and "disconnect the internet")

For the agent these are identical — the backend becomes unreachable.

1. Stop the backend (or drop the VPS's egress / pull the network).
2. Emit some trades on the VPS (as in §11).
3. Observe the agent **hold, not lose**:
   ```bash
   curl http://127.0.0.1:8765/stats
   # queued: >0   dropped: 0   breaker: "closed"→"open" after 5 failed cycles
   ```
   Telemetry accumulates in the durable queue; after `breaker_threshold` (5)
   consecutive failed upload cycles the circuit trips **open** and the agent stops
   hammering the dead backend.
4. Restore the backend (or the network). Within a cooldown the breaker probes,
   closes, and the queue **drains**:
   ```bash
   curl http://127.0.0.1:8765/stats        # queued → 0, uploaded climbs, dropped: 0
   curl https://ops.example.com/api/events  # the trades emitted during the outage are all present
   ```

> Verified: 6 trades emitted while the backend was down were **all** delivered
> after restart (`dropped: 0`).

### b) Stop the backend mid-stream

A subset of (a): kill the backend process while heartbeats are flowing. The
machine card goes **offline ~20s** later (stale heartbeat). On backend restart the
agent re-registers on its next cycle and the card returns to **online** — the
agent keeps its same `agentId` (persisted in the queue DB), so it's the same host,
not a duplicate.

### c) Restart the VPS

```bash
sudo reboot          # Linux         |  Restart-Computer   # Windows
```

After boot:
- systemd/NSSM relaunch the agent automatically (§8).
- The agent reopens its **SQLite WAL queue** — anything not yet uploaded survives
  the reboot and flushes once the backend is reachable (`dropped: 0`).
- The strategy is restarted by **your** process supervisor; on `monitor.start()`
  it re-announces and trades resume streaming.

Confirm with `systemctl status raj-agent` (or `nssm status RajLocalAgent`) and a
fresh `/stats`.

---

## 15. Troubleshooting guide

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `curl 127.0.0.1:8765/health` refused | Agent not running, or port in use | `systemctl status raj-agent` / `nssm status`; check `logs/`; change `agent.port` if 8765 is taken. |
| `/stats` shows `breaker: "open"` | Backend unreachable (down, DNS, firewall, TLS) | Verify `curl <backend>/api/health` from the VPS; check egress 443 and `backend.url` ends in `/api`. Queued events flush automatically on recovery. |
| Strategy runs but **nothing** appears | `RAJ_MACHINE`/`RAJ_LOCAL_TOKEN` mismatch with the agent, or agent down | Make `RAJ_MACHINE` == `machine.name` and `RAJ_LOCAL_TOKEN` == `agent.local_token`; confirm agent `/health`. |
| Local POSTs rejected `401` | `RAJ_LOCAL_TOKEN` doesn't match `agent.local_token` | Align the two values (or unset both for local dev — auth is disabled when no token is configured). |
| Host appears then goes **offline** | Heartbeats stalled > ~20s (agent crashed/paused) | Check the service is `Restart=always`; inspect `logs/` and `journalctl -u raj-agent`. |
| `cpu` stuck at `0` on the **first** reading | `psutil.cpu_percent` warm-up | Normal — populates on the next 10s snapshot. Install `psutil` if all metrics are sparse. |
| Machine name shows **twice** on the dashboard | A seeded mock fixture shares the name | Expected — your live host is the `mch-agent-<slug>` card; mock cards are demo placeholders (never overwritten). Use a distinct `machine.name` to avoid confusion. |
| Dashboard loads but data is **mock / not updating** | `VITE_USE_MOCK` not `false`, or `VITE_API_BASE_URL` empty/missing `/api` | Set `VITE_USE_MOCK=false` and `VITE_API_BASE_URL=https://…/api`; rebuild. The websocket URL is derived as `…/api/ws`. |
| Dashboard REST works, **no live updates** | Websocket blocked (proxy strips `Upgrade`) | Ensure the reverse proxy forwards `Upgrade`/`Connection` headers for `/api/ws`. |
| Browser console **CORS** error | Dashboard origin not in `CORS_ORIGINS` | Add the exact origin to `backend/.env` `CORS_ORIGINS` and restart the backend. |
| `dropped > 0` in `/stats` | Sustained backend outage longer than the queue can hold (`queue.max_size`) | Increase `queue.max_size`, or restore the backend sooner; oldest items are dropped first by design. |
| Agent log: `ingest error: WinError 10053/10054` (Windows) | Localhost keep-alive reset under rapid posts | Fixed in this build (agent responds `Connection: close`; SDK disables proxy lookups and flushes on `stop()`). Ensure you deployed the updated `raj_monitor/`. |

**Where to look:** agent logs in `<workdir>/logs/` (rotating), service logs via
`journalctl -u raj-agent -f` (Linux) or the NSSM stdout/stderr files (Windows),
and the agent's own `GET /stats` for queue/breaker/upload counters.

---

## Appendix — what was changed for reliable VPS operation

Per the deployment mandate, **only configuration/reliability fixes** were made; no
architecture, SDK surface, or backend contract changed. The localhost SDK→agent
hop was dropping rapid follow-up telemetry on Windows; root cause and fixes:

- **`raj_monitor/monitor_sdk.py`** — the SDK now reuses one `urllib` opener with
  **proxy auto-detection disabled** (`ProxyHandler({})`). The default opener calls
  `getproxies()` on every request, which on Windows performs WinINET/WPAD registry
  lookups that added **hundreds of ms per localhost post** and throttled bursts to
  ~2 msg/s. With it disabled, steady-state posts dropped to **~3–5 ms**. `stop()`
  now **drains the queue (bounded) and joins the sender** so a burst immediately
  before shutdown can't be stranded behind the stop sentinel.
- **`raj_monitor/agent.py`** & **`raj_monitor/security.py`** — the agent's local
  API responds with `Connection: close`, and the SDK declares it too, so both ends
  agree to close each one-shot connection instead of racing a half-open
  keep-alive socket (the source of the `WinError 10053/10054` resets).

These changes are validated by `raj_monitor/tests/test_smoke.py` (8/8) plus the
end-to-end drills in §§9–14.
