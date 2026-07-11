# Raj Local Agent — Windows installation

Run **one** agent per Windows machine (e.g. a trading PC or a Windows VPS). It
listens on `127.0.0.1:8765` for your strategies and forwards telemetry to the
Operations Center backend.

---

## 1. Prerequisites

- Python 3.10+ (`python --version`)
- The `raj_monitor` package folder copied to the machine, e.g. `C:\raj-monitor\raj_monitor`

## 2. Create a virtual environment & install deps

```powershell
cd C:\raj-monitor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install psutil PyYAML
```

> The SDK needs no dependencies; `psutil` + `PyYAML` only enrich the **agent**.

## 3. Configure

Copy and edit the config:

```powershell
copy raj_monitor\config.yaml config.yaml
notepad config.yaml
```

Set at minimum:
- `backend.url` → your FastAPI backend, e.g. `https://ops.example.com/api`
- `backend.token` → the agent auth token
- `machine.name` → e.g. `Personal Computer`
- `agent.local_token` → a shared secret (the strategy uses the same value)

## 4. Run it (console)

```powershell
python -m raj_monitor.agent --config config.yaml
```

You should see `Agent ready. Local API on http://127.0.0.1:8765`. Check health:

```powershell
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/stats
```

## 5. Run it as a Windows service (recommended)

The simplest reliable approach is **NSSM** (the Non-Sucking Service Manager):

```powershell
# 1. Download nssm.exe from https://nssm.cc and put it on PATH.
# 2. Install the service pointing at the launcher .bat:
nssm install RajLocalAgent "C:\raj-monitor\raj_monitor\service\raj-agent.bat"
nssm set RajLocalAgent AppDirectory "C:\raj-monitor"
nssm set RajLocalAgent Start SERVICE_AUTO_START
nssm set RajLocalAgent AppStdout "C:\raj-monitor\logs\service.out.log"
nssm set RajLocalAgent AppStderr "C:\raj-monitor\logs\service.err.log"

# 3. Start / manage:
nssm start RajLocalAgent
nssm status RajLocalAgent
nssm stop RajLocalAgent
```

**Alternative (no NSSM): Task Scheduler.** Create a Basic Task → Trigger *At
startup* → Action *Start a program* → `C:\raj-monitor\raj_monitor\service\raj-agent.bat`.
Tick *Run whether user is logged on or not*.

## 6. Point a strategy at the agent

In the strategy's environment (same machine):

```powershell
$env:RAJ_STRATEGY   = "MR-FX"
$env:RAJ_MACHINE    = "Personal Computer"   # match config.yaml machine.name
$env:RAJ_LOCAL_TOKEN= "the-same-local_token"
python your_strategy.py
```

That's it — see `examples/strategy_integration.py` for the calls to add.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `curl /health` refused | Agent not running, or `agent.port` in use — change the port. |
| Strategy events not appearing | Wrong `RAJ_MACHINE`/`RAJ_LOCAL_TOKEN`, or agent can't reach backend (check `/stats` → `breaker`). |
| `breaker: open` in `/stats` | Backend unreachable; events stay queued and upload when it returns. |
| High CPU | Increase `intervals.metrics_sec`; disable per-process listing by uninstalling psutil. |
