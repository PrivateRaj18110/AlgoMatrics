# Ops dashboard (Raj Quant OS)

A Bloomberg-style trading operations center served at **`/ops`** alongside the
main console. It monitors external trading machines (via the `raj-monitor`
SDK + agent) and mirrors live platform data (strategies, trades, risk,
analytics, brokers, accounts) from the AlgoMatrics control plane.

```
strategies on remote hosts ──> raj_monitor SDK ──> local agent ──> POST /ops/api/agent/*
                                                                        │
console data  <── /api/v1 (X-API-Key) <── ops-api ──> /ops (React SPA) ─┘
```

## Layout

| Path | What it is |
|---|---|
| `ops/frontend/` | React 19 + Vite dashboard (`@algo-matrics/ops-dashboard`), built with `base: '/ops/'` |
| `ops/backend/` | FastAPI service: telemetry ingest (`/api/agent/*`, `/api/ingest/*`), websocket (`/api/ws`), AlgoMatrics proxy |
| `packages/raj_monitor/` | Standalone SDK + host agent (`pip install ./packages/raj_monitor`, console script `raj-agent`) |
| `deploy/docker/ops-api.Dockerfile` | ops backend image (compose service `ops-api`) |

The ops code keeps its own lightweight tooling and is excluded from the
platform's strict ruff/mypy gates for now (`pyproject.toml` excludes;
follow-up tracked in the PR).

## Running

Docker Compose runs everything: `docker compose -f deploy/compose/docker-compose.yml up --build`
- Console: <http://localhost:8080/> — Ops dashboard: <http://localhost:8080/ops>
- Ops API health: `GET http://localhost:8080/ops/api/health`

Local development:

```bash
cd ops/backend && python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn main:app --reload --port 8001          # ops API on :8001

cd ops/frontend && npm install && npm run dev  # http://localhost:5173/ops/
```

The Vite dev server proxies `/ops/api` → `http://localhost:8001`.

**Kubernetes.** The ops-api runs as `deploy/k8s/45-ops.yaml` (Deployment + Service +
Config/Secret) and `65-ops-ingress.yaml` routes `/ops/api` to it; the `/ops` SPA
static assets are served by the frontend (external / CDN), same as the console. See
[production-infrastructure.md](production-infrastructure.md) for the full sequence,
required images, and the Compose↔Kubernetes parity table.

## Data sources

**Live by default.** The deployed dashboard builds the frontend in live mode, so
`/ops` always calls the ops-api (`/ops/api`) rather than bundled fixtures. The
ops-api serves **live AlgoMatrics data when the credentials below are set, and
its own mock otherwise** — so `/ops` renders either way and switches to real data
the moment the key is provisioned. (For pure-UI work you can still ship the
frontend's bundled mock: build the image with `--build-arg VITE_USE_MOCK=true`,
or set `VITE_USE_MOCK=true` for `npm run dev`.)

**Live platform data.** Set three variables (root `.env` for compose;
`ops/backend/.env` for local runs):

```bash
ALGOMATRICS_API_URL=http://api:8000/api/v1   # compose; http://localhost:8000/api/v1 locally
ALGOMATRICS_API_KEY=<org-scoped read key>
ALGOMATRICS_ORG_ID=<organization uuid>
```

Create the key with a `read` scope: `POST /api/v1/api-keys` (Settings → API
keys in the console, or curl with a JWT). The ops backend then maps
`/dashboard/summary`, `/strategies`, `/strategy-runs`, `/trades`,
`/risk/*`, `/analytics/*`, `/broker-connections`, `/accounts` into the
dashboard's schemas, with a ~5 s cache and automatic mock fallback when the
control plane is unreachable or the credentials are absent.
Machines/events/logs/alerts always come from telemetry, not the platform.

**Machine telemetry.** Install the agent on each trading host (London VPS,
Google Cloud, personal PC):

```bash
pip install ./packages/raj_monitor    # or copy the folder to the host
raj-agent --config config.yaml        # backend.url: https://<domain>/ops/api
```

Strategies then call `from raj_monitor import monitor; monitor.start()` etc.
See [packages/raj_monitor/README.md](../../packages/raj_monitor/README.md),
the Windows/Linux install guides in the same folder, and
[ops/docs/](../../ops/docs/) for the full SDK reference.

## Security note

`/ops` has **no authentication of its own** (the Supabase auth in its
Settings page is an inert placeholder). It is safe on localhost; before
exposing it publicly, add auth at the edge — e.g. `auth_basic` on the `/ops`
locations in `deploy/nginx/nginx.conf` or an allowlist on the edge proxy.
The `ALGOMATRICS_API_KEY` lives only in the ops backend container and is
never sent to the browser.
