# AWS / AlgoMatrics Phase 3 acceptance report

Date: 2026-08-13

## Executive status

Phase 3 is accepted for the AWS-side foundation scope.

The repository now contains a secured, durable AWS operations platform for
receiving Google VM telemetry, monitoring live status, detecting gaps/failures,
landing EOD datasets, deriving bounded quant analytics, replaying finalized
data, running synthetic quant-only simulations, and presenting these workflows
in the Ops dashboard.

The execution boundary is preserved:

* Google remains the only trading/execution authority.
* AWS receives, stores, monitors, reconciles and analyzes telemetry/data.
* AWS does not log in to brokers, route orders, run strategies, trigger risk
  controls or send commands back to Google.
* `ops/backend/tests/test_execution_isolation.py` enforces this structurally.

## Acceptance evidence

| Gate | Result |
|---|---:|
| Alembic heads | `b4d8e2a7c9f1 (head)` |
| Targeted Phase 3 backend suite | `20 passed, 1 warning in 162.95s` |
| Full backend suite | `177 passed, 1 warning in 2462.76s` |
| Frontend lint | Passed |
| Frontend production build | Passed |

The one warning is from the current FastAPI/Starlette testclient stack:
`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`.
It is not caused by Phase 3 business logic.

## Completed scope matrix

| Area | Accepted implementation |
|---|---|
| Agent authentication | `/api/agent/*` and `/api/ingest/*` require token authentication and fail closed in production. Machine-scoped tokens are supported. |
| Dashboard authentication | Websocket and REST dashboard reads require viewer credentials in production, with shared-token and JWT public-key paths. |
| Durable ingestion | Events, logs, trades, metrics, machines, sessions, sync state and dead letters persist through the ops repository layer. |
| Idempotency | `ingest_dedup` prevents duplicate envelope processing across restarts. |
| Gap detection | `sync_state` tracks sequence high-water marks, gap counts, missing counts and queue depth. |
| Heartbeat/status | Machine status, heartbeat age, degraded/offline state and current session are derived read models. |
| Real-time dashboard | Authenticated websocket clients receive snapshots and event notifications; reconnect gets a fresh snapshot. |
| Recovery view | `/api/recovery/summary` reports offline duration, queue pressure, gap counters, EOD backlog and recovery state without controlling Google. |
| EOD data sync | `/api/eod/*` supports manifests, resumable chunks, checksum validation, completion, finalization and reconciliation. |
| Object storage | EOD bytes can use local storage or S3-compatible object storage through `DatasetStorage`. |
| Quant reports | Finalized EOD datasets generate `quant_reports` with coverage, trade metrics, market replay and analytics sections. |
| Quant analytics | `/api/quant/analytics/{category}` exposes `performance`, `strategy`, `execution`, `signals`, `risk`, `sessions` and `dataQuality` readiness. |
| Quant honesty | Metrics are explicitly marked `AVAILABLE`, `NOT_AVAILABLE` or `INSUFFICIENT_DATA`; missing fees/slippage/signals/positions are not fabricated. |
| Synthetic replay | `/api/quant/replays/synthetic` runs bounded deterministic quant-only price-path simulations inside AWS. |
| AWS-only smoke | `scripts.run_phase3_simulation` drives authenticated ingestion, websocket, recovery, EOD and quant routes without a live Google VM. |
| Performance measurement | `scripts.measure_phase3_performance` records ingest, websocket, dashboard read, EOD and quant smoke timings. |
| Retention | Destructive retention is disabled by default; dedup, telemetry, dead letters, sessions, EOD metadata/raw bytes and quant reports have explicit policies. |
| Deployment | Docker Compose, Nginx, Kubernetes ops API, database, prune job and ingress manifests are present. |
| Documentation | Ops dashboard, ingestion/recovery/EOD/quant, retention, simulation and deployment behavior are documented. |

## Database and migration state

The Phase 3 ops database is additive. Current migration chain:

| Revision | Purpose |
|---|---|
| `e1fd66220c23` | Initial telemetry schema |
| `b7c2e4a91f30` | Phase 2 ingestion hardening |
| `c0b5f6a7e8d9` | Phase 3 machine status timeline |
| `d8a41f2c9e7b` | Phase 3 EOD dataset landing |
| `f4a9c3d2b8e1` | Phase 3 recovery state |
| `e9b2c7d5a104` | Phase 3 quant reports |
| `ad9f3b6c2e41` | Phase 3 retention markers |
| `b4d8e2a7c9f1` | Phase 3 quant analytics sections |

Important tables/read models:

* `machines`
* `events`
* `logs`
* `trades`
* `metrics`
* `ingest_dedup`
* `sync_state`
* `sessions`
* `ingest_dead_letters`
* `eod_datasets`
* `eod_dataset_files`
* `quant_reports`

## Accepted API surface

Phase 3 public Ops API paths include:

* `/api/agent/batch`
* `/api/agent/events`
* `/api/agent/heartbeat`
* `/api/agent/logs`
* `/api/agent/metrics`
* `/api/agent/register`
* `/api/agent/trades`
* `/api/eod/manifests`
* `/api/eod/datasets`
* `/api/eod/datasets/{dataset_id}`
* `/api/eod/datasets/{dataset_id}/files/{file_id}/chunks`
* `/api/eod/datasets/{dataset_id}/complete`
* `/api/eod/datasets/{dataset_id}/finalize`
* `/api/eod/reconciliation`
* `/api/events`
* `/api/logs`
* `/api/machines`
* `/api/machines/{machine_id}`
* `/api/recovery/summary`
* `/api/quant/reports`
* `/api/quant/analytics/{category}`
* `/api/quant/datasets/{dataset_id}/report`
* `/api/quant/replays/datasets/{dataset_id}`
* `/api/quant/replays/synthetic`
* `/api/ws`

The legacy dashboard/proxy read endpoints remain available behind dashboard
viewer authentication:

* `/api/dashboard/overview`
* `/api/strategies`
* `/api/trades`
* `/api/execution/overview`
* `/api/risk/overview`
* `/api/analytics`
* `/api/brokers`
* `/api/accounts`
* `/api/alerts`
* `/api/settings`

## Frontend acceptance

The Ops dashboard now has real API-backed pages for:

* Monitoring
* Events
* Logs
* Machines
* Recovery
* Data Sync / EOD reconciliation
* Quant Lab
* Dashboard overview
* Strategies
* Trades
* Execution
* Risk
* Analytics
* Brokers
* Accounts
* Alerts
* Settings

Quant Lab specifically consumes:

* `/api/quant/reports` for materialized dataset reports;
* `/api/quant/analytics/{category}` for category readiness and bounded metrics;
* `/api/quant/replays/synthetic` for deterministic synthetic replay.

## Security acceptance

Accepted controls:

* Agent token authentication.
* Machine-scoped agent credentials.
* Fail-closed production startup for missing database/auth credentials.
* Authenticated websocket handshake.
* Authenticated production REST dashboard reads.
* Optional JWT public-key verification for dashboard identity.
* No credentials logged in structured ingest logs.
* Bounded batch size and payload handling.
* Dead-letter storage for permanently invalid envelopes.
* Durable idempotency keys.
* No AWS-to-Google control path.
* Execution-isolation regression tests.

Operational note: the shared dashboard token path is an interim credential model.
For commercial multi-user access, deploy `OPS_JWT_PUBLIC_KEY` and issue
short-lived user JWTs from the platform login flow.

## Deployment acceptance

Deployment assets are present for:

* Docker Compose stack.
* Ops API container.
* Nginx routing for `/ops` and `/ops/api`.
* Kubernetes ops API Deployment/Service.
* Kubernetes ops database manifest.
* Kubernetes retention/prune CronJob.
* Kubernetes ingress routing.
* Environment examples for backend and frontend.

Production cutover checklist:

1. Provision the ops PostgreSQL database.
2. Populate `DATABASE_URL`.
3. Populate `RAJ_AGENT_TOKENS` or `RAJ_AGENT_TOKEN`.
4. Populate `RAJ_DASHBOARD_TOKEN` or deploy `OPS_JWT_PUBLIC_KEY`.
5. Configure EOD storage: local for single-replica/dev, S3-compatible object
   storage for production.
6. Run `alembic upgrade head`.
7. Deploy ops-api and frontend bundle.
8. Configure the Google agent with the scoped backend token and `/ops/api` URL.
9. Run `scripts.run_phase3_simulation` in staging.
10. Run `scripts.measure_phase3_performance` in staging.
11. Enable only the retention policies that match business retention rules.
12. Configure backups for PostgreSQL and object storage.

## Known limits and deliberate non-goals

These are not blockers for Phase 3 acceptance because they are either production
cutover tasks or future scale-out work:

* The websocket broadcaster is single-node and in-memory. Multi-replica ops-api
  needs Redis/pub-sub or another shared broadcaster.
* EOD object storage support exists, but real bucket/IAM/lifecycle provisioning
  must be done in the target cloud account.
* Quant scans are bounded in-process. Large research jobs should move to a
  DuckDB/object-storage worker pipeline.
* The Google agent still needs producers/schedulers for every future Phase 3
  dataset category the business decides to emit.
* Shared dashboard tokens should be replaced with platform JWTs for per-user
  RBAC in commercial production.
* The Starlette/httpx testclient deprecation warning should be tracked as a
  dependency-maintenance issue.

## Final acceptance decision

Accepted.

The Phase 3 AWS-side foundation is complete for MVP integration: ingestion is
secured and durable, telemetry/recovery/EOD/quant read models are live,
dashboard pages are connected to real APIs, deployment assets are present, and
the test suite validates the execution boundary and core failure modes.
