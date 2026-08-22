# Final AWS / AlgoMatrics pre-live readiness report

Date: 2026-08-14  
Scope: AWS-side operations, telemetry, EOD data, dashboard and quant platform only  
Decision: **GO — AWS PRE-LIVE READY**

This is a code-freeze gate report. No production deployment was performed. No live
Google trading VM was contacted. No broker, strategy, order, execution or risk
control logic was modified or invoked.

## 1. Executive summary

The AWS side is code complete, test complete and pre-live ready for the final
integration/deployment phase.

The six required AWS capabilities are complete locally:

1. Heartbeat & Status
2. Real-Time Data
3. Offline / Recovery
4. EOD Data Sync
5. Dashboard
6. Quant Layer

The final deployment phase should now require only:

* infrastructure configuration;
* secrets;
* Google agent connection;
* production storage configuration;
* deployment;
* real-world end-to-end verification.

No major AWS application feature is intentionally left for the live deployment
phase.

## 2. Previous baseline

The previous accepted Phase 3 baseline stated:

| Gate | Previous result |
|---|---:|
| Full backend suite | 177 passed |
| Frontend lint | Passed |
| Frontend production build | Passed |
| Alembic head | `b4d8e2a7c9f1` |

Those results were not assumed. The current repository was re-audited and
re-verified.

## 3. Current architecture

Authority boundary remains unchanged:

```text
Google / Local Trading VM
  trading authority
  execution authority
  broker authority
          |
          | authenticated telemetry, status, logs, EOD files only
          v
AWS Ops Platform
  monitoring authority
  data authority
  analytics authority
          |
          v
Ops Dashboard / Quant Lab
  read-only operational and analytical views
```

There is no AWS-to-Google trading/control path. AWS does not place, cancel,
modify or close orders; does not change strategy parameters; does not change risk
limits; does not call broker APIs; and does not control the Google VM.

Main AWS-side layers:

```text
Agent / Google-compatible telemetry
  -> FastAPI auth + schema validation
  -> ingestion service
  -> PostgreSQL repositories
  -> machine/session/sync/dead-letter/EOD/quant read models
  -> authenticated REST + WebSocket dashboard APIs
  -> React Ops dashboard
```

Raw EOD data is separate from operational state:

```text
raw EOD files -> storage port -> normalized metadata -> quant reports -> dashboard
```

## 4. Capability audit

Initial pre-fix audit found these genuine gaps:

| Capability | Audit finding | Action |
|---|---|---|
| EOD Data Sync | Status enum contained `DISCOVERED`, `VALIDATING`, `QUARANTINED`, but those states were not all reachable through API workflows. | Added discovery, validating transition and quarantine workflow. |
| Dashboard | Machine monitoring existed, but dedicated machine/session drilldowns were missing. | Added machine detail and session detail routes/pages. |
| Dashboard | Positions were represented by Live Trades, but no named Positions route. | Added `/:market/positions` route alias and clearer label. |
| Dashboard safety | Settings page showed disabled/local strategy/risk controls. | Replaced with read-only execution-authority boundary notice. |
| API validation | EOD/session filters accepted arbitrary status strings. | Constrained them to known status values. |
| Deployment config | Ops CI/Docker images were pinned to Python 3.12. | Aligned ops CI/Docker images to Python 3.13. |

No duplicate ingestion, dashboard, storage or quant systems were introduced.
Existing Phase 2/3 components were extended in place.

## 5. Changes made

Backend:

* Added read-only session APIs:
  * `GET /api/sessions`
  * `GET /api/sessions/{session_id}`
* Added session service/read models using the existing `sessions` table.
* Added EOD discovery and quarantine workflows:
  * `POST /api/eod/discoveries`
  * `POST /api/eod/datasets/{dataset_id}/quarantine`
* Made `VALIDATING` a real transient EOD state after full upload and before
  completion validation.
* Preserved idempotent manifest behavior and conflict behavior:
  * same dataset + same checksum/manifest returns existing dataset;
  * same dataset + different manifest/checksum moves to conflict/failure
    visibility, never silent overwrite.
* Expanded execution-isolation tests across dashboard, quant, EOD, replay and
  analytics surfaces.
* Tightened query validation for EOD and session status filters.
* Removed an unused legacy null-session repository alias.

Frontend:

* Added machine detail drilldown page.
* Added session detail drilldown page.
* Added session service/types/hooks.
* Added links from dashboard/monitoring machine cards to machine detail.
* Added `/:market/positions` route alias and renamed the nav/page label to
  Positions while preserving `/:market/live-trades`.
* Replaced apparent strategy/risk controls in Settings with a read-only
  authority-boundary panel.
* Replaced auth placeholder text with honest dashboard security mode text:
  shared dashboard token/JWT-compatible pre-live auth, not commercial RBAC.

Deployment/config:

* Updated ops-backend GitHub Actions Python runtime from 3.12 to 3.13.
* Updated ops API Dockerfiles from Python 3.12 to Python 3.13.
* Updated mock runtime fixture text to Python 3.13.

## 6. Files created

Created in this final pre-live iteration:

* `docs/operations/final-prelive-aws-report.md`
* `ops/backend/app/api/routers/sessions.py`
* `ops/backend/app/schemas/session.py`
* `ops/backend/app/services/session_service.py`
* `ops/backend/tests/test_sessions_api.py`
* `ops/frontend/src/hooks/useSessions.ts`
* `ops/frontend/src/pages/Machines/MachineDetailPage.tsx`
* `ops/frontend/src/pages/Sessions/SessionDetailPage.tsx`
* `ops/frontend/src/services/sessions.service.ts`
* `ops/frontend/src/types/session.ts`

## 7. Files modified

Modified directly in this final pre-live iteration:

* `.github/workflows/ci.yml`
* `deploy/docker/ops-api.Dockerfile`
* `ops/backend/Dockerfile`
* `ops/backend/app/api/router.py`
* `ops/backend/app/api/routers/eod.py`
* `ops/backend/app/repositories/__init__.py`
* `ops/backend/app/repositories/mock_data.py`
* `ops/backend/app/repositories/sql.py`
* `ops/backend/app/schemas/eod.py`
* `ops/backend/app/services/eod_service.py`
* `ops/backend/tests/test_eod_sync.py`
* `ops/backend/tests/test_execution_isolation.py`
* `ops/backend/tests/test_release_hotfix.py`
* `ops/frontend/src/App.tsx`
* `ops/frontend/src/components/navigation/navConfig.ts`
* `ops/frontend/src/hooks/queryKeys.ts`
* `ops/frontend/src/hooks/useMachines.ts`
* `ops/frontend/src/pages/Dashboard/DashboardPage.tsx`
* `ops/frontend/src/pages/Machines/MachinesPage.tsx`
* `ops/frontend/src/pages/Settings/SettingsPage.tsx`
* `ops/frontend/src/pages/market/LiveTradesPage.tsx`
* `ops/frontend/src/services/index.ts`
* `ops/frontend/src/types/index.ts`

Note: the worktree already contained many uncommitted Phase 2/3 files before
this final iteration. They were preserved.

## 8. Database changes

No new Alembic revision was required in this final iteration.

Reason:

* EOD status vocabulary already existed in schemas/models.
* The `sessions` table already existed.
* Existing EOD dataset columns already support status and status reason.
* Existing quant report/schema migrations remain valid.

Verified current migration state:

| Check | Result |
|---|---|
| Alembic single head | `b4d8e2a7c9f1 (head)` |
| Disposable DB upgrade | Passed |
| Safe one-step downgrade | Passed |
| Re-upgrade to head | Passed |
| Final current revision | `b4d8e2a7c9f1 (head)` |

Important durable tables/read models:

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

## 9. API changes

New/extended routes:

| Route | Method | Purpose | Auth |
|---|---:|---|---|
| `/api/eod/discoveries` | POST | Record discovered EOD dataset before manifest registration. | Agent token + machine scope |
| `/api/eod/datasets/{dataset_id}/quarantine` | POST | Mark invalid/unsafe dataset as quarantined. | Agent token + machine scope |
| `/api/sessions` | GET | List trading sessions. | Dashboard viewer |
| `/api/sessions/{session_id}` | GET | Session detail with recent events and EOD datasets. | Dashboard viewer |

Current OpenAPI inventory includes:

* `/api/agent/*`
* `/api/ingest/*`
* `/api/ws`
* `/api/dashboard/overview`
* `/api/machines`
* `/api/machines/{machine_id}`
* `/api/sessions`
* `/api/sessions/{session_id}`
* `/api/events`
* `/api/logs`
* `/api/recovery/summary`
* `/api/eod/*`
* `/api/quant/*`
* legacy/read-only dashboard proxy routes for strategies, trades, brokers,
  accounts, risk, execution, analytics, alerts and settings.

Trading display surfaces are GET-only. The only non-GET dashboard route is
`PUT /api/settings`, which persists UI/application settings and does not expose
order, strategy, broker, execution or risk-control behavior.

## 10. Dashboard changes

Verified dashboard views:

| Required view | Current implementation |
|---|---|
| System Overview | `/` dashboard overview |
| Machine Detail | `/monitoring/:machineId` |
| Session Detail | `/sessions/:sessionId` |
| Real-Time Activity | authenticated WebSocket + event terminal/pages |
| Trades | `/:market/closed-trades` and legacy `/trades` redirect |
| Positions | `/:market/positions` plus compatible `/:market/live-trades` |
| PnL | dashboard/trades/portfolio cards |
| Risk | `/:market/risk` |
| Errors | `/events`, `/logs`, recovery/dead-letter visibility |
| EOD Data | `/data-sync` and `/eod` redirect |
| Alerts | `/alerts` |
| Quant Lab | `/quant` |

Dashboard safety changes:

* No BUY/SELL/CLOSE/CANCEL/MODIFY controls are present.
* No strategy activation UI was added.
* No risk-limit modification UI is present.
* Settings page now explicitly states AWS is read-only for execution authority.
* Frontend uses service-layer API clients; mock data remains explicit via
  `USE_MOCK` and visible in the connection status.

## 11. Quant changes

The Quant Layer was audited and re-verified.

Required categories are available:

* performance
* strategy
* execution
* signals
* risk
* sessions
* data quality

Availability semantics remain:

* `AVAILABLE`
* `NOT_AVAILABLE`
* `INSUFFICIENT_DATA`

The layer does not fabricate analytics. Missing source data remains
`NOT_AVAILABLE`; too few observations remain `INSUFFICIENT_DATA`.

Quant remains read-only. It does not import or invoke broker clients, order
routers, execution engines, strategy engines, risk controllers, Flattrade, MT5
or trading APIs.

## 12. EOD changes

The EOD workflow now supports all required states:

| State | Verified path |
|---|---|
| `DISCOVERED` | `POST /api/eod/discoveries` |
| `MANIFESTED` | `POST /api/eod/manifests` |
| `UPLOADING` | chunk upload in progress |
| `PARTIAL` | incomplete dataset after partial completion attempt |
| `VALIDATING` | all bytes uploaded, checksum/completion validation pending |
| `READY` | all files checksum-validated and dataset completed |
| `COMPLETE` | finalized dataset |
| `FAILED` | checksum/file validation failure |
| `QUARANTINED` | explicit quarantine route |
| `CONFLICT` | same dataset ID with incompatible manifest metadata |

Safety rules verified:

* same dataset + same manifest/checksum is idempotent;
* same dataset + different manifest/checksum is conflict/failure-visible;
* uploads are resumable by offset;
* upload gaps are rejected;
* partial uploads survive restart in the durable path;
* checksum mismatch is not silently overwritten;
* completion and finalization require validated files;
* raw storage is behind a storage abstraction with local and S3-compatible
  configuration paths.

No production storage credentials were invented.

## 13. Security audit

Verified controls:

* Agent endpoints require `X-Raj-Agent-Token`.
* Machine-scoped tokens are supported and enforce payload machine scope.
* WebSocket authenticates before accepting and sends no frames to rejected
  clients.
* Dashboard REST reads are authenticated in production and can be forced in
  staging/dev via `OPS_REST_AUTH_REQUIRED=true`.
* Shared dashboard token and optional RS256 public-key JWT verification are
  supported.
* Credentials are not included in viewer subject strings.
* Production startup fails closed without database, agent credentials or
  dashboard credentials.
* Transient persistence failures return 503 so the agent retries instead of
  deleting unpersisted data.
* Permanent invalid envelopes are dead-lettered and visible.
* Secret scan found no suspicious hardcoded credential assignments outside env
  templates.
* Root `.env` was inspected by key name only; values were not printed.

Honest limitation:

* The shared dashboard token path authenticates a dashboard, not a commercial
  per-user RBAC identity.
* Optional JWT public-key support prepares the architecture for per-user identity
  without rewriting dashboard routes.
* Commercial RBAC should be enabled during final production identity integration;
  it is not claimed as already complete.

## 14. Execution isolation

Execution-isolation tests were run and expanded.

Verified read-only surfaces:

* dashboard REST routes;
* quant routes/services;
* EOD landing/reconciliation;
* recovery routes/services;
* session routes/services;
* replay/simulation/performance harnesses;
* analytics read paths.

Forbidden imports/calls remain blocked for those surfaces:

* broker clients;
* order routers;
* execution engine;
* strategy engine;
* risk controller;
* Flattrade;
* MT5;
* trading APIs.

No execution-path violation was found.

## 15. Failure testing

Verified by tests and simulation:

* AWS transient DB failure returns 503.
* Agent replay is safe after transient failure.
* Duplicate envelope replay does not duplicate events/trades.
* Duplicate batch replay does not duplicate trades or fills.
* Sequence gaps are visible.
* Sequence gaps do not reject valid later envelopes.
* Older delayed/replayed sequences do not rewind high-water marks.
* Dead letters persist across restart.
* Sync state persists across restart.
* Sessions persist across restart.
* EOD partial upload/resume works.
* EOD checksum failure is visible.
* EOD conflict cannot silently overwrite.
* WebSocket reconnect gets a fresh snapshot.

## 16. E2E testing

Deterministic AWS-only simulation was run locally against a disposable database
and local EOD storage.

Command family:

```text
alembic upgrade head
python -m scripts.run_phase3_simulation --run-id final-prelive-20260814 --json
```

Verified simulation result:

| Signal | Result |
|---|---:|
| Initial offline batch processed | 9 |
| Intentional permanent rejection | 1 dead-letter |
| Duplicate replay safe | true |
| Sequence gap visible | true |
| WebSocket authenticated | true |
| WebSocket observed messages | 7 |
| Dashboard bounded payload preview | true |
| EOD final status | `COMPLETE` |
| EOD checksum passed | true |
| EOD reconciliation total | 1 |
| Quant status | `READY` |
| Quant closed trades | 2 |
| Quant gross PnL | 1.0 |
| Authority boundary broker/control calls | false |

The simulation did not contact a real Google VM or broker.

## 17. Performance results

Measured with local/staging TestClient, SQLite disposable DB and local EOD
storage. These are smoke measurements, not production load-test numbers.

Command family:

```text
alembic upgrade head
python -m scripts.measure_phase3_performance \
  --run-id final-prelive-20260814 \
  --batches 4 \
  --batch-size 25 \
  --json
```

Measured result:

| Metric | Result |
|---|---:|
| Envelopes submitted | 100 |
| Envelopes accepted | 100 |
| Ingestion throughput | 22.517 envelopes/sec |
| Ingestion request latency p50 | 1097.070 ms |
| Ingestion request latency p95 | 1159.023 ms |
| Write latency per envelope | 44.397990 ms |
| Duplicate replay count | 25 |
| Duplicate replay latency | 95.760 ms |
| WebSocket broadcast latency | 82.657 ms |
| Dashboard machines read | 16.114 ms |
| Dashboard events read | 34.186 ms |
| Recovery summary read | 43.930 ms |
| EOD manifest latency | 95.540 ms |
| EOD upload latency | 224.982 ms |
| EOD complete latency | 44.489 ms |
| EOD finalize + analyze latency | 190.160 ms |
| Quant report read latency | 14.806 ms |

Current architecture is sufficient for the pre-live MVP. Future scale work
should be evidence-driven after production/staging metrics exist.

## 18. Test results

Current verified results:

| Gate | Result |
|---|---:|
| Backend full regression | `182 passed, 0 failed, 0 errors, 1 warning in 1619.67s` |
| Targeted EOD/session/isolation/release slice | `24 passed, 0 failed, 0 errors, 1 warning in 182.64s` |
| Frontend lint | Passed |
| Frontend production build | Passed |
| Alembic heads | `b4d8e2a7c9f1 (head)` |
| Alembic upgrade/downgrade/upgrade | Passed on disposable local DB |
| Static YAML parse | 26 files, 41 documents parsed |
| Redacted hardcoded-secret scan | 0 suspicious literal credential assignments |
| AWS-only E2E simulation | Passed |
| AWS-side performance harness | Passed |

The one warning is:

```text
StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated
```

It is a dependency-maintenance warning, not a pre-live business logic failure.

## 19. Deployment readiness

Prepared assets:

* Dockerfiles for backend/frontend/ops-api/AI-CIO.
* Docker Compose manifests.
* Nginx routing/TLS example.
* Kubernetes namespace/config/migration/API/workers/ops-api/ops-db/prune/ingress
  manifests.
* Observability manifests for Prometheus/Grafana/Loki/Promtail/Alertmanager.
* GitHub Actions CI with Python 3.13 and ops backend/frontend jobs.
* Environment templates for ops backend/frontend.
* Health/readiness/liveness probes in manifests.
* Ops PostgreSQL separation from the platform database.
* EOD storage configuration for local single-replica and S3-compatible object
  storage.

Verified locally:

* YAML syntax parsed for deployment/CI manifests.
* Alembic migration lifecycle passed against a disposable DB.
* Python 3.13+ runtime pins are aligned in ops CI/Dockerfiles.
* Application tests, frontend lint/build, simulation and performance harness
  passed.

Requires real infrastructure / release environment:

* Docker CLI/image build validation. Docker CLI was not available in this local
  shell, so `docker compose config` and image builds were not run here.
* Kubernetes server-side validation/apply.
* Production secrets.
* Real PostgreSQL/RDS/managed database.
* Real object storage bucket/IAM/lifecycle if using S3-compatible storage.
* DNS/TLS/ingress.
* Google agent connection.
* Real-world E2E verification after deployment.

## 20. Google integration contract

Google/local agent needs exactly:

| Item | Contract |
|---|---|
| Backend URL | Final deployed ops API URL, usually `https://<host>/ops/api` or equivalent ingress path. Local API path is `/api`. |
| Agent token | `X-Raj-Agent-Token`; prefer machine-scoped `RAJ_AGENT_TOKENS="machine:token"`. |
| Machine name | Must match the token scope exactly. AWS derives machine ID as `mch-agent-<slug>`. |
| Agent ID | Send `X-Raj-Agent-Id` and payload `agentId`. |
| Schema version | Old protocol-1 envelopes are still accepted. New envelopes may send `schema_version`; simulation used `3`. |
| Sequence ID | Optional for old agents; recommended for upgraded agents as `sequence_id`. |
| Session ID | Optional for old agents; recommended as `session_id` for session correlation. |
| Queue depth | Optional old field; recommended as `queueDepth` on batch and heartbeat/status payloads. |
| Heartbeat interval | Default `HEARTBEAT_INTERVAL_SECONDS=10`; degraded after `30s`; offline after `120s`, all configurable. |
| Batch size | Server ceiling `INGEST_MAX_BATCH_ITEMS=1000`; current agent batch size can remain below this. |
| EOD manifest format | `datasetId`, `machine`, `agentId`, optional `sessionId`, `tradingDate`, optional `createdAt`, `schemaVersion`, `files[]`. |
| EOD file fields | `fileId`, `relativePath`, `datasetType`, `sizeBytes`, `sha256`, optional `rowCount`. |
| EOD upload method | `POST /api/eod/manifests`, `PUT /api/eod/datasets/{dataset_id}/files/{file_id}/chunks?offset=N`, `POST /complete`, `POST /finalize`. Optional `POST /discoveries` before manifest. |
| Storage method | Google uploads to AWS API only. AWS stores bytes via configured local/S3-compatible storage port. |

Google does not need to change broker or strategy execution behavior for AWS
pre-live readiness.

## 21. Remaining work

Remaining work is deployment/infrastructure/integration, not major AWS
application feature work:

* Provision ops PostgreSQL.
* Configure secrets:
  * `DATABASE_URL`
  * `RAJ_AGENT_TOKENS` or `RAJ_AGENT_TOKEN`
  * `RAJ_DASHBOARD_TOKEN` and/or `OPS_JWT_PUBLIC_KEY`
  * optional `ALGOMATRICS_API_KEY` / `ALGOMATRICS_ORG_ID`
  * optional S3 credentials if not using workload identity
* Configure production EOD storage.
* Build/push release images in CI or deployment workstation.
* Apply migrations in deployment environment.
* Deploy ops-api/frontend/ingress.
* Configure Google agent with backend URL, token, machine and agent IDs.
* Run real-world staging/live-adjacent E2E verification.
* Enable commercial per-user JWT/RBAC when platform identity is ready.

Future improvements, not pre-live blockers:

* Shared pub/sub broadcaster before horizontally scaling WebSocket across
  multiple ops-api replicas.
* Larger DuckDB/object-storage worker pipeline for large historical research
  workloads.
* Dependency maintenance for Starlette/httpx testclient deprecation warning.

## 22. Final acceptance matrix

| Area | Status | Evidence | Remaining |
|---|---|---|---|
| Heartbeat & Status | COMPLETE | Full regression, status timeline tests, simulation online/offline/recovery states. | Configure final thresholds per deployment. |
| Real-Time Data | COMPLETE | Agent compatibility tests, WebSocket auth/reconnect tests, simulation observed authenticated messages. | Real Google feed verification after deployment. |
| Offline / Recovery | COMPLETE | Ingest durability, recovery status, transient 503 retry, sequence-gap tests. | Real outage drill after deployment. |
| EOD Data Sync | COMPLETE | EOD object storage/sync tests; all required states reachable; simulation finalized `COMPLETE`. | Configure production storage/IAM. |
| Dashboard | COMPLETE | Frontend lint/build; machine/session/EOD/quant/recovery/positions routes wired. | Real browser smoke against deployed API. |
| Quant Layer | COMPLETE | Quant replay tests, full regression, simulation quant `READY`, availability semantics preserved. | Larger analytics pipeline optional later. |
| Security | COMPLETE | Agent auth, REST auth, WebSocket pre-accept auth, production fail-closed, secret scan. | Enable production JWT/RBAC when identity is ready. |
| Execution Isolation | COMPLETE | Expanded isolation tests across dashboard/quant/EOD/replay/analytics passed. | Keep as regression gate. |
| Database | COMPLETE | Single Alembic head; upgrade/downgrade/upgrade passed; durable restart tests passed. | Provision production DB/backups. |
| API | COMPLETE | OpenAPI inventory verified; bounded GET/read routes; EOD/session additions tested. | Publish deployed endpoint URL. |
| Frontend | COMPLETE | `npm run lint` and `npm run build` passed after final changes. | Production browser smoke. |
| Replay | COMPLETE | Quant replay tests and AWS-only simulation passed; no execution path. | Real recorded dataset replay after deployment. |
| E2E Simulation | COMPLETE | `scripts.run_phase3_simulation` passed with ingest -> persistence -> WS -> dashboard -> EOD -> quant. | Real Google-agent E2E after deployment. |
| Deployment Readiness | COMPLETE | Manifests present; YAML parsed; CI/Docker config prepared; Python 3.13 aligned. | Docker build/apply require CI or deployment workstation; real infra/secrets required. |

## 23. GO / NO-GO

**GO — AWS PRE-LIVE READY**

This does not mean live. It means AWS is ready for the final
integration/deployment phase.

Do not deploy until production infrastructure, secrets, storage and Google agent
configuration are ready and the final real-world E2E verification plan is
approved.

