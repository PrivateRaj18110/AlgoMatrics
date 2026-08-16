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

> **Telemetry ingestion is documented separately.** The `/ops/api/agent/*` tier,
> its authentication, durable persistence, idempotency, sequence tracking and
> dead-letter handling are covered in
> **[ops-ingestion.md](ops-ingestion.md)** — read that before deploying or
> configuring a trading host. In particular, `ops-api` now **refuses to start in
> production** without `DATABASE_URL`, an agent credential and a dashboard
> credential.

## Layout

| Path | What it is |
|---|---|
| `ops/frontend/` | React 19 + Vite dashboard (`@algo-matrics/ops-dashboard`), built with `base: '/ops/'` |
| `ops/backend/` | FastAPI service: telemetry ingest (`/api/agent/*`, `/api/ingest/*`), websocket (`/api/ws`), AlgoMatrics proxy |
| `packages/raj_monitor/` | Standalone SDK + host agent (`pip install ./packages/raj_monitor`, console script `raj-agent`) |
| `deploy/docker/ops-api.Dockerfile` | ops backend image (compose service `ops-api`) |

Key global pages:

| Page | Backend source |
|---|---|
| Monitoring | `/api/machines`, `/api/events`, `/api/ws` |
| Recovery | `/api/recovery/summary` |
| Data Sync | `/api/eod/datasets`, `/api/eod/reconciliation` |
| Quant Lab | `/api/quant/reports`, `/api/quant/analytics/{category}`, `/api/quant/replays/synthetic` |

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

**Offline/recovery state.** The Recovery page is a derived read model over
machine heartbeats, sync-state counters and EOD catalog backlog. It shows
heartbeat age, offline duration, queue depth, recovered/missing events, current
session and EOD backlog. It does not send recovery commands to a trading host.

**EOD + quant data.** The Data Sync page reads the EOD manifest/catalog created
by `/api/eod/*`. When a dataset finalizes successfully, the ops backend derives
a bounded quant report (`quant_reports`) from finalized CSV/JSONL files in EOD
storage. Quant Lab displays those reports, exposes category-level read-only
analytics for `performance`, `strategy`, `execution`, `signals`, `risk`,
`sessions` and `dataQuality`, and can run deterministic synthetic quant-only
replays entirely inside AWS for pre-Google integration testing. Metrics are
explicitly marked `AVAILABLE`, `NOT_AVAILABLE` or `INSUFFICIENT_DATA`; the
dashboard does not fabricate missing fees, slippage, signal or position data.

For the broader AWS-side smoke, run `python -m scripts.run_phase3_simulation`
from `ops/backend` against a migrated disposable `DATABASE_URL`. That harness
drives the real authenticated agent routes, websocket, recovery read model, EOD
upload/finalize APIs, dashboard reads and quant report generation without a live
Google VM.

EOD bytes can land on local filesystem storage for development/single-replica
deployments or on S3-compatible object storage for production by setting
`EOD_STORAGE_BACKEND=s3` plus the `EOD_S3_*` configuration. Object storage uses
chunk objects and a small per-file index, so retries remain resumable and
checksum validation remains deterministic without forcing raw data into
PostgreSQL.

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

**Telemetry endpoints are authenticated** as of Phase 2:

* `/ops/api/agent/*` and `/ops/api/ingest/*` require `X-Raj-Agent-Token` and
  fail closed — an unconfigured server rejects every request rather than
  accepting them. Credentials can be scoped to a single machine.
* `/ops/api/ws` requires a viewer credential before the handshake is accepted,
  so live telemetry never reaches an anonymous client.
* Dashboard REST reads use the same viewer abstraction. In production they
  require either `Authorization: Bearer <token>` or `X-Raj-Dashboard-Token`;
  staging/dev can force the same path with `OPS_REST_AUTH_REQUIRED=true`.

See [ops-ingestion.md](ops-ingestion.md) for configuration and the deployment
order.

**The interim shared dashboard token is not per-user RBAC.** It authenticates
the dashboard bundle, not an individual person. For real user identity, deploy
`OPS_JWT_PUBLIC_KEY` and have the platform login send short-lived access tokens
as `VITE_OPS_API_TOKEN` / `VITE_OPS_WS_TOKEN`. Until then, still put the SPA
itself behind edge auth (`auth_basic`, an allowlist, or the console login).

The `ALGOMATRICS_API_KEY` lives only in the ops backend container and is never
sent to the browser. `VITE_OPS_API_TOKEN` and `VITE_OPS_WS_TOKEN`, by contrast,
can be embedded in the frontend bundle — use JWTs where possible, and treat a
shared build-time value as an interim dashboard credential only.
