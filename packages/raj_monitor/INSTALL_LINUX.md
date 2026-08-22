# Raj Local Agent — Linux / Google Cloud / VPS installation

Run **one** agent per host (London VPS, Google Cloud instance, etc.). It listens
on `127.0.0.1:8765` for local strategies and forwards telemetry to the backend.

---

## 1. Prerequisites

- Python 3.10+ (`python3 --version`)
- The `raj_monitor` package copied to the host, e.g. `/opt/raj-monitor/raj_monitor`

## 2. Create a virtual environment & install deps

```bash
sudo mkdir -p /opt/raj-monitor && sudo chown "$USER" /opt/raj-monitor
cd /opt/raj-monitor
# copy the raj_monitor/ package here first
python3 -m venv .venv
.venv/bin/pip install psutil PyYAML
```

## 3. Configure

```bash
cp raj_monitor/config.yaml config.yaml
nano config.yaml
```

Set `backend.url`, `backend.token`, `machine.name` (e.g. `London VPS`), and a
shared `agent.local_token`.

## 4. Test in the foreground

```bash
.venv/bin/python -m raj_monitor.agent --config config.yaml
# in another shell:
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/stats
```

## 5. Install as a systemd service (recommended)

```bash
# Create a dedicated user (optional but recommended):
sudo useradd --system --home /opt/raj-monitor --shell /usr/sbin/nologin raj || true
sudo chown -R raj:raj /opt/raj-monitor

# Install the unit (edit paths/User inside it first if needed):
sudo cp raj_monitor/service/raj-agent.service /etc/systemd/system/raj-agent.service
sudo systemctl daemon-reload
sudo systemctl enable --now raj-agent

# Manage / observe:
systemctl status raj-agent
journalctl -u raj-agent -f
```

The unit sets `Restart=always`, so the agent comes back after crashes and
reboots. Its on-disk queue means **no telemetry is lost** across restarts.

## 6. Point a strategy at the agent

```bash
export RAJ_STRATEGY="MR-FX"
export RAJ_MACHINE="London VPS"       # match config.yaml machine.name
export RAJ_LOCAL_TOKEN="the-same-local_token"
python3 your_strategy.py
```

See `examples/strategy_integration.py` for the exact calls.

## Google Cloud notes

- A GCE VM is just a Linux host — the steps above apply unchanged.
- Keep the backend reachable over the VM's egress (firewall allows outbound 443).
- The agent's local API stays on `127.0.0.1` — do **not** expose 8765 publicly.
- For autoscaled/managed instances, bake the venv + config into the image or a
  startup script so each instance starts its own agent.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `curl /health` refused | `systemctl status raj-agent`; check the journal for errors. |
| `breaker: open` in `/stats` | Backend unreachable; queued events upload when it recovers. |
| Permission denied on queue db | Ensure the service `User` owns `WorkingDirectory`. |
| `getloadavg`/metrics sparse | Install `psutil` in the venv for full metrics. |
