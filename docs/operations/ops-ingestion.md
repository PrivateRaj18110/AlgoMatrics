# Google VM → AWS telemetry ingestion (Phase 2)

Operational runbook for the secured, durable ingestion layer that receives
telemetry from the Google trading VM.

> **Architectural rule, no exceptions.** Google is the only execution authority.
> The AWS ingestion path may read and store telemetry and must never reach broker
> login, order placement, strategy execution, signal routing or risk control.
> `ops/backend/tests/test_execution_isolation.py` enforces this structurally and
> fails the build if a future change introduces such a dependency.

---

## 1. What changed in Phase 2

| Area | Before | After |
|---|---|---|
| Agent auth | `X-Raj-Agent-Token` sent by the agent, **ignored** by the server | Verified on every `/api/agent/*` and `/api/ingest/*` request; fail closed |
| Websocket | Anonymous — anyone could stream live telemetry | Credential required before `accept()`; no frame reaches an unauthenticated client |
| Persistence | `DATABASE_URL=""` in prod: RAM ring buffers, lost on restart | PostgreSQL, dedicated ops database |
| Dedup | Disabled in prod (mock mode returns "not seen" for everything) | `ingest_dedup` enforced, durable across restarts |
| Trades / metrics | Silently discarded in prod | Persisted |
| Batch ack | `processed = len(items)` regardless of outcome | Per-item outcome; only genuinely persisted items counted |
| Failures | `except Exception: continue` — silent drop | Permanent → dead-letter table; transient → 503 so the agent retries |
| Loss detection | None | `sequence_id` high-water mark + gap counters in `sync_state` |
| Sessions | None | `sessions` table, populated when the agent reports `session_id` |
| Startup | Quietly degraded to mock mode | Production refuses to start misconfigured |

---

## 2. Required configuration

Production (`ENVIRONMENT=production`) **will not start** without all three:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Ops telemetry database. **Not** the platform database. |
| `RAJ_AGENT_TOKENS` *(or `RAJ_AGENT_TOKEN`)* | Agent ingestion credential |
| `RAJ_DASHBOARD_TOKEN` *(or `OPS_JWT_PUBLIC_KEY`)* | Websocket viewer credential |
| `OPS_REST_AUTH_REQUIRED` | Force REST dashboard reads to require a viewer credential outside production |

This is deliberate: the previous deployment ran with none of them and looked
healthy while storing nothing durably and accepting anonymous writes.

### Generating credentials

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Machine-scoped vs fleet-wide

Prefer machine-scoped. A leaked scoped token can only forge one machine's
telemetry; a request whose payload names a different machine gets 403.

```ini
# machine name must match the agent's machine.name / RAJ_MACHINE exactly
RAJ_AGENT_TOKENS=gcp-trading-01:<token-a>,london-vps:<token-b>
```

Secrets are injected through the existing secret manager into the `ops-secrets`
Kubernetes Secret. Nothing is committed with a real value.

---

## 3. Deployment order

Backward compatibility is preserved in both directions, so **AWS and Google do
not have to be upgraded together** — with one ordering constraint.

```
1. Provision the ops telemetry database        deploy/k8s/46-ops-db.yaml
2. Populate ops-secrets                        DATABASE_URL, RAJ_AGENT_TOKENS,
                                               RAJ_DASHBOARD_TOKEN
3. Deploy ops-api                              deploy/k8s/45-ops.yaml
      the ops-migrate initContainer runs `alembic upgrade head` first;
      a failed migration blocks the rollout rather than half-starting the API
4. Configure the dashboard                     VITE_OPS_API_TOKEN / VITE_OPS_WS_TOKEN
5. Configure the Google agent                  RAJ_BACKEND_TOKEN + backend URL
```

> **Step 5 is the breaking moment for Google.** From the instant step 3 lands,
> an agent without a token gets 401. Its durable SQLite queue *holds* the
> telemetry (a 4xx raises in `transport.py`, and `agent.py::_drain_once` only
> deletes queue rows after a successful upload), so nothing is lost — but the
> backlog grows until step 5. Keep the gap short.

Agent configuration (`raj_monitor/config.yaml`, or the equivalent environment
variables):

```yaml
backend:
  url: "https://app.algomatrics.com/ops/api"   # must include /api
  token: "<the token issued for THIS machine>"
  verify_ssl: true                              # never disable
machine:
  name: "gcp-trading-01"                        # must match RAJ_AGENT_TOKENS
```

Rollback: redeploy the previous ops-api image. The Phase 2 migration is purely
additive, so the older build ignores the new tables and keeps running.

---

## 4. API contract

### Authentication

| Header | Value |
|---|---|
| `X-Raj-Agent-Token` | The machine's credential. Required. |
| `X-Raj-Agent-Id` | Advisory agent identity. Not a credential — never used alone for authorization. |
| `Content-Encoding: gzip` | Optional; the agent gzips above 512 bytes. Decompressed transparently. |

| Response | Meaning | Agent behaviour |
|---|---|---|
| `200` | Batch handled; see the outcome breakdown | Deletes the batch from its queue |
| `401` | Missing/invalid/unconfigured credential | Fails fast, **keeps** the queue |
| `403` | Credential not authorized for that machine | Fails fast, keeps the queue |
| `413` | Batch above `INGEST_MAX_BATCH_ITEMS` | Fails fast, keeps the queue |
| `503` | Transient store failure | Retries with backoff, keeps the queue |

### Envelope

Existing wire fields are unchanged — `id`, `kind`, `ts`, `strategy`, `machine`,
`account`, `protocol`, `data`. Renaming any of them would force a lock-step
upgrade, which is exactly the coupling this integration avoids.

Three optional additions; an agent that omits them is fully supported:

| Field | Purpose |
|---|---|
| `sequence_id` | Monotonic per (machine, agent). Enables gap detection. **Not** the dedup key. |
| `schema_version` | Version of this `kind`'s payload, so a payload can evolve without a protocol bump. |
| `session_id` | Trading session key, e.g. `2026-08-09-NSE`. |

`AgentBatch` also accepts an optional `queueDepth` — the agent's own backlog at
send time. A rising value alongside healthy heartbeats means AWS is the
bottleneck.

### Offline / recovery view

`GET /api/recovery/summary` is the AWS-side recovery read model. It derives:

* heartbeat age and offline duration from the latest machine heartbeat;
* queue depth and oldest pending age from heartbeat/system-status payloads;
* accepted/duplicate/failed/missing event counters from `sync_state`;
* EOD backlog from non-finalized EOD datasets; and
* explicit recovery state from `recovery` envelopes when the agent reports it.

This endpoint is observational only. It never calls Google, never drains the
agent queue, never triggers EOD upload, and never controls broker, strategy or
risk state.

### Acknowledgement

The original five fields are unchanged (`accepted`, `received`, `kind`,
`processed`, `machineId`), so the dashboard and agent keep working. `processed`
now means **genuinely persisted**, not "received".

```jsonc
{
  "accepted": true,        // false when a transient failure occurred
  "received": "2026-08-09T09:15:00Z",
  "kind": "batch",
  "processed": 198,        // ACCEPTED only
  "machineId": "mch-agent-gcp-trading-01",
  "total": 200,
  "duplicate": 1,          // already seen — safe, expected under at-least-once
  "rejected": 1,           // permanently unprocessable; dead-lettered
  "failed": 0,             // transient; batch returns 503 when > 0
  "outcomes": [{"id": "env-…", "status": "rejected", "reason": "unknown envelope kind 'x'"}],
  "lastSequenceId": 123456,
  "sequenceGap": false
}
```

### Websocket

Credentials travel in `Sec-WebSocket-Protocol` as `raj-token, <credential>` —
browsers cannot set headers on a `WebSocket`, and a query-string token would leak
into access logs. Non-browser clients may use `Authorization: Bearer <token>`.

---

## 5. Reliability model

Unchanged in principle, now actually enforced:

```
durable queue on Google  +  at-least-once delivery  +  server-side idempotency
```

Exactly-once network delivery is not attempted, because it cannot be achieved.

| Scenario | Behaviour |
|---|---|
| Duplicate envelope | `ingest_dedup` skips it — no rows, no broadcast, no metric movement |
| Whole batch replayed | Every item deduplicated; blotter and event counts unchanged |
| Crash before ack | Agent redelivers; server deduplicates |
| Database unavailable | 503; agent keeps the batch and retries with backoff |
| Malformed envelope | Dead-lettered with a reason; batch still succeeds for the rest |
| Sequence gap | Recorded in `sync_state`; **valid data is still accepted** |
| AWS restart | State is in PostgreSQL and survives |
| Google offline | Machine degrades/offlines from configurable heartbeat age thresholds |
| Dashboard websocket disconnect | Client can reconnect, receives a fresh machine snapshot, then new events |
| EOD checksum mismatch | Dataset/file fail visibly; re-uploading correct bytes can recover and finalize |

**Why a gap never rejects.** Missing envelopes may still arrive on a later
retry, and refusing valid data because earlier data is late turns a small loss
into a large one. The gap is recorded and made visible instead.

---

## 6. Schema

Migration `b7c2e4a91f30_phase2_ingestion_hardening` (additive only).

| Table | Purpose | Retention |
|---|---|---|
| `machines` | Host state and last heartbeat | Indefinite |
| `events` | Timeline + alerts | `OPERATIONAL_EVENT_RETENTION_DAYS` (default 0 / disabled) |
| `logs` | Log viewer | `TELEMETRY_RETENTION_DAYS` (default 0 / disabled) |
| `trades` | Blotter | `TELEMETRY_RETENTION_DAYS` (default 0 / disabled) |
| `metrics` | Host + custom metric series | `TELEMETRY_RETENTION_DAYS` (default 0 / disabled) |
| `ingest_dedup` | Idempotency keys | `INGEST_DEDUP_RETENTION_DAYS` (default 7) |
| `sync_state` | Per (machine, agent) sequence + gap counters | Indefinite (one row per agent) |
| `sessions` | Trading sessions | `SESSION_RETENTION_DAYS` for closed sessions only (default 0 / disabled) |
| `ingest_dead_letters` | Permanently unprocessable envelopes | `DEAD_LETTER_RETENTION_DAYS` after triage (default 0 / disabled) |
| `eod_datasets` / `eod_dataset_files` | EOD manifest/catalog metadata | `EOD_METADATA_RETENTION_DAYS` for terminal datasets (default 0 / disabled) |
| EOD raw bytes | Files/objects behind `DatasetStorage` | `EOD_RAW_RETENTION_DAYS` for terminal datasets (default 0 / disabled) |
| `quant_reports` | Derived analytics/replay summaries | `QUANT_REPORT_RETENTION_DAYS` (default 0 / disabled) |

### Dedup retention is a correctness setting

`prune_dedup()` deletes idempotency rows older than the window. The window must
exceed the agent's longest realistic offline period: an envelope replayed after
its dedup row is pruned is processed **a second time**. The agent's queue holds
100,000 envelopes ≈ 14 trading sessions of telemetry, so raise the retention
before allowing an outage longer than the default 7 days.

Pruning runs nightly at 01:20 UTC via `deploy/k8s/47-ops-prune.yaml` (after the
Indian market close, before the AI-CIO pipeline's 02:00 run so the two do not
contend). To run it by hand:

```bash
python -m scripts.prune_dedup --days 7 --dry-run
```

### Destructive retention is disabled by default

`scripts.prune_retention` covers the broader ops tables and raw EOD bytes. Every
policy defaults to `0`, which means "do nothing". This is intentional: raw
research data and analytical lineage must not disappear because of a bundled
guess.

Run a dry run first:

```bash
python -m scripts.prune_retention --dry-run --json
```

Then set only the policies you actually want. The job runs nightly at 01:35 UTC
in `deploy/k8s/47-ops-prune.yaml`; with all destructive policies disabled it
reports zero changes. EOD raw retention deletes storage bytes and stamps
`raw_deleted_at` on the dataset metadata; EOD metadata retention deletes terminal
dataset catalog rows and their file rows. These two policies are intentionally
separate because object-store lifecycle, raw research retention, and dashboard
catalog retention can differ.

---

## 7. AWS-only Phase 3 local simulation

The full Google VM is not required to verify the AWS-side platform. Run the
deterministic local harness after migrating a disposable ops database:

```bash
cd ops/backend
python -m alembic upgrade head
python -m scripts.run_phase3_simulation --json --run-id local-smoke
```

Required environment:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Durable test/staging ops database; required |
| `RAJ_AGENT_TOKEN` or matching `RAJ_AGENT_TOKENS` | Authenticates synthetic Google-agent writes |
| `RAJ_DASHBOARD_TOKEN` | Authenticates dashboard REST/WebSocket reads |
| `EOD_STORAGE_ROOT` or `EOD_STORAGE_BACKEND=s3` | EOD raw-byte landing target |

The script uses the real FastAPI routes in-process. It exercises:

* authenticated `/api/agent/batch` ingestion;
* authenticated `/api/ws` machine/event streaming;
* stale heartbeat -> offline recovery summary;
* recovery reconnect event -> online recovery summary;
* duplicate replay idempotency;
* visible sequence gap;
* durable dead letter for an unsupported envelope;
* resumable EOD upload, checksum validation, completion and finalization;
* checksum-failure retry and authenticated websocket reconnect are covered by
  focused regression tests;
* dashboard event/machine/EOD reads;
* automatic quant report generation from finalized EOD files, including
  read-only `performance`, `strategy`, `execution`, `signals`, `risk`,
  `sessions` and `dataQuality` analytics availability sections.

Safety rules:

* it refuses `ENVIRONMENT=production`;
* it refuses to run without `DATABASE_URL`;
* it writes only synthetic telemetry/EOD rows under the provided `run-id`;
* it never imports or calls broker, execution, order-routing, strategy-control
  or risk-control modules.

The JSON result is intentionally acceptance-report friendly: it includes ACK
breakdowns, websocket message types, recovery states, EOD reconciliation, quant
metrics and explicit authority-boundary flags.

---

## 8. Performance measurement

Use the local/staging measurement harness to generate reproducible numbers for
the Phase 3 acceptance report:

```bash
cd ops/backend
python -m alembic upgrade head
python -m scripts.measure_phase3_performance \
  --json \
  --run-id local-perf \
  --batches 4 \
  --batch-size 25
```

Required environment is the same as the simulation harness: `DATABASE_URL`,
agent credentials, dashboard credential, and an EOD storage target. The harness
refuses `ENVIRONMENT=production` and refuses missing `DATABASE_URL`.

It reports:

| Metric group | What is measured |
|---|---|
| `ingestion` | accepted envelopes, envelopes/sec, request p50/p95/max, write latency per envelope, duplicate replay latency |
| `websocketBroadcast` | authenticated connection and event notification latency |
| `dashboardReads` | `/api/machines`, filtered `/api/events`, `/api/recovery/summary` read latency |
| `eodAndQuant` | manifest latency, upload latency, completion latency, finalization + quant analysis latency, quant report read latency |

These numbers are **local/staging smoke measurements**, not production SLOs.
Use them to catch regressions and to size the first deployment. Run a separate
real-infrastructure test after PostgreSQL, object storage and Google telemetry
are connected.

---

## 9. Observability

Structured on the `ops.ingest` logger. Never logs credentials or payload bodies.

```
ingest batch machine_id=… agent_id=… total=200 accepted=198 duplicate=1 rejected=1 failed=0 gap=False
```

Worth alerting on:

| Signal | Why |
|---|---|
| `sync_state.gap_count` rising | Telemetry is being lost between Google and AWS |
| `sync_state.queue_depth` rising | AWS is the bottleneck, or the agent cannot deliver |
| `ingest_dead_letters` non-empty | Envelopes are being discarded — triage the reason |
| 401 rate above zero | Misconfigured agent, or someone probing the endpoint |
| 503 rate above zero | Telemetry store trouble; the agent is holding data |
| `last_batch_at` stale | Google is offline, or delivery is broken |

Useful queries:

```sql
-- delivery health per agent
SELECT machine, agent_id, last_sequence_id, gap_count, missing_count,
       queue_depth, last_batch_at
FROM sync_state ORDER BY last_batch_at DESC;

-- what is being discarded, and why
SELECT reason, kind, COUNT(*) FROM ingest_dead_letters
GROUP BY reason, kind ORDER BY COUNT(*) DESC;
```

---

## 10. Rate limiting

Sized from measured telemetry rather than guessed: steady state is ~0.31
envelopes/sec in batches of 200, i.e. about one request every 3 seconds per agent
(`raj_monitor` `upload_sec=3`).

| Layer | Setting | Rationale |
|---|---|---|
| nginx (compose) | `limit_req zone=api burst=100 nodelay` | Absorbs a queue drain (~500 batches for a full backlog) |
| ingress (k8s) | `limit-rps: 20`, `limit-burst-multiplier: 10` | Same headroom |
| Body size | 8 MB | Far above any legitimate gzipped batch |
| Application | `INGEST_MAX_BATCH_ITEMS=1000` | Bounds the work one request can demand |

Raise these *before* adding agents, not after seeing 503s.

---

## 11. Network security

Unchanged and already correct: **Google → AWS outbound HTTPS only.** No inbound
monitoring port on Google, and no AWS → Google control path exists or is planned.

The ingress allowlist annotation in `deploy/k8s/65-ops-ingress.yaml` is left
**unset on purpose**. The Google VM's static egress IP is not established in this
repository, and an allowlist against an ephemeral IP is worse than none — it
creates false confidence and breaks ingestion at the first NAT reassignment.
Populate it once the IP is confirmed. Authentication is mandatory and independent
of it; the allowlist is a second layer, never the primary control.

Note that the allowlist would also restrict the dashboard websocket, which shares
the path prefix. If browsers need `/ops/api/ws` from arbitrary networks, split
the ingress: allowlisted for `/ops/api/agent` and `/ops/api/ingest`, open (but
authenticated) for the rest.

---

## 12. Known limitations

1. **Shared dashboard token.** `RAJ_DASHBOARD_TOKEN` in a browser SPA
   authenticates *a dashboard*, not *a person*, and cannot be revoked per user.
   It now protects both websocket and production REST dashboard reads, but it is
   still not granular RBAC. The `OPS_JWT_PUBLIC_KEY` path already exists in code
   for per-user platform JWTs; deploy the public key and have the SPA pass
   short-lived platform tokens for user-level identity.
2. **HMAC request signing not implemented.** `X-Raj-Timestamp` / `X-Raj-Signature`
   is Phase 2B: the shipped agent cannot sign, and adding server-side enforcement
   now would break it. Token + TLS is the Phase 2A control.
3. **Single replica.** The websocket broadcaster keeps its client set in memory,
   so ops-api is not horizontally scaled. Scaling out needs a shared pub/sub.
4. **No Redis.** The target sketch mentions Redis for hot machine state; it is
   not implemented. The `machines` row already answers "current state" directly,
   and at 0.31 envelopes/sec a cache would add a failure mode without a
   demonstrated need. Revisit if dashboard read latency becomes a problem.
5. **Websocket broadcaster is single-node.** EOD landing can now use local
   filesystem storage or S3-compatible object storage, but the websocket
   broadcaster still keeps its client registry in-process. Production
   multi-replica `ops-api` still needs a shared pub/sub broadcaster.
6. **Bounded in-API quant scans.** The Phase 3 quant report foundation parses
   finalized EOD CSV/JSONL files with explicit row/file/point limits. It now
   materializes bounded analytics sections for performance, strategy, execution,
   signals, risk, sessions and data quality, but each metric carries an
   availability status instead of inventing absent data. This is enough for
   AWS-side validation, dashboard reports and deterministic replay; larger
   research workloads should move behind DuckDB/object-storage workers.

---

## 13. Deliberately out of scope

* **Raw tick / option-quote streaming.** Measured at ~30.6 MB/day/symbol versus
  ~2 MB/day of telemetry, with no live operational use. It belongs in an
  end-of-day batch path, not the real-time endpoint.
* **Real object-storage bucket provisioning.** The EOD storage port supports
  `local` and S3-compatible object storage (`EOD_STORAGE_BACKEND=s3`), but this
  repository does not create a real bucket or lifecycle policy. Configure
  `EOD_S3_BUCKET`, region/endpoint, workload identity or secret-managed AWS
  credentials, then run an infrastructure verification upload.
* **Full DuckDB/object-storage quant pipeline.** `quant_reports` now stores
  derived metrics, replay summaries and explicit analytics availability sections
  for finalized EOD datasets. `/api/quant/analytics/{category}` exposes the
  read-only categories to the dashboard, and `/api/quant/replays/synthetic`
  supports deterministic quant-only price-path replay. A bulk DuckDB worker over
  object storage remains future scale-out work.
* **Google-side emission for the full Phase 3 vocabulary.** The AWS schema and
  routers accept the Phase 3 event vocabulary and EOD manifests. The trading
  VPS agent still needs the corresponding producers/schedulers for every data
  category.
