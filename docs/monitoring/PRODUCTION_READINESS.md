# Production readiness — monitoring.v1 receiver

**Nothing was deployed.** No DNS, firewall, production secret, or production VM was touched. This document records what would have to be true before that changes, and what is verified today.

---

## 1. Verified locally

| Item | Evidence |
|---|---|
| Receiver accepts valid monitoring.v1 and rejects everything else | 60 tests, all passing |
| Published schemas enforce the contract | 46 tests, all passing |
| Evidence is immutable | ORM-level enforcement + test |
| Projections rebuild identically from evidence | test |
| Idempotency across ack loss | test |
| Conflicts retained, never resolved | test |
| Sequence gaps visible, never fatal | test |
| UNKNOWN survives to the screen | backend + frontend tests |
| Dead feed goes STALE with its last update time | backend + frontend tests |
| Environment isolation at the query | test |
| No control surface | structural tests on OpenAPI and on the schemas |
| Migration applies, rolls back, and re-applies | run against SQLite |
| Whole ops suite green | 327 passed, 0 failed |

## 2. Not verified — and what it would take

| Item | Status | Needs |
|---|---|---|
| PostgreSQL behaviour | **UNKNOWN** | the migration and receiver have only run against SQLite |
| Concurrent publishers | **UNKNOWN** | the `IntegrityError` duplicate path is implemented but never raced |
| Throughput, latency, memory, storage growth | **NOT MEASURED** | a load harness — see `PERFORMANCE_REPORT.md` |
| Receiver restart mid-batch | **NOT TESTED** | a durability test like the agent path's |
| Database slow / unavailable *while configured* | **NOT TESTED** | fault injection |
| Disk full | **NOT TESTED** | fault injection |
| Real publisher interoperability | **UNKNOWN** | the LLS side publishing against these schemas |
| TLS, DNS, certificate, VM identity, firewall | **REQUIRES PRODUCTION ACCESS** | deployment credentials, which were not available and were not sought |
| Backup and restore of the monitoring tables | **NOT DONE** | see `BACKUP_RESTORE.md` |

## 3. Open items before production

1. **Confirm the canonical-JSON definition with the LLS side.** The contract said "canonical JSON" without defining it; the receiver pins UTF-8 / sorted keys / compact separators / unescaped non-ASCII. If the publisher canonicalises differently, every integrity check fails. This is the single most likely interoperability break, and it is cheap to settle in advance.
2. **Quarantine retention.** `monitoring_quarantine` and `monitoring_raw_requests` have no pruning. A publisher stuck on an unsupported major sending full batches grows raw storage by one request body per request, without bound.
3. **Bounded gzip decompression.** The shared request middleware decompresses fully before any size check. Authenticated-only and rate-limited at nginx, but a gzip bomb would be expanded in memory before rejection. Fix and exposure are described in `SECURITY_REPORT.md` §6.
4. **Run the migration against PostgreSQL** on a copy of production data, and time it. It is additive (seven new tables, no ALTER), so it should be fast, but "should be" is not a measurement.
5. **Take a backup before migrating.** The upgrade is additive and safe; the **downgrade drops `monitoring_evidence`**, which destroys received evidence. Everything else is derived.
6. **Decide the environment scope.** `MONITORING_SOURCE_ENVIRONMENTS` is optional. Production should set it, so a staging publisher cannot write production rows even with a valid credential.

## 4. Deployment prerequisites

Configuration required on the ops-api service:

```
MONITORING_SOURCE_TOKENS="lls-monitoring-prod:<token>"
MONITORING_SOURCE_ENVIRONMENTS="lls-monitoring-prod:production"
MONITORING_ADMIN_TOKEN=<token>
OPS_DATABASE_URL=<existing ops database>
MONITORING_SCHEMA_DIR=<path to schemas/monitoring-export/v1 in the image>
```

Generate credentials with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

No nginx change is required: `/ops/api/` already proxies to ops-api, so the ingress is reachable at `https://<host>/ops/api/v1/monitoring/export`.

`MONITORING_SCHEMA_DIR` matters if `ops/backend` is containerised without the repository root — the receiver reads the published schemas from disk and returns 503 if it cannot find them. Verify this in the built image, not just in the repo.

## 5. Failure isolation

If algomatric.in goes down, its storage fails, or its network is unavailable, **LLS continues**. The receiver is not in the trading path: it holds no callback into LLS, makes no outbound connection to it, and returns 503 so the publisher's durable queue absorbs the outage.

If LLS fails, stored history here is unaffected — evidence is append-only and no LLS process can reach it.

Both are design properties verified by code structure and by the pre-existing `test_execution_isolation.py`. Neither has been verified by actually taking a component down.

## 6. What must not be claimed

Per the contract's own rule, the site is not deployed until the VM, DNS, TLS, service, ingestion, restart test and security checks are each independently verified. **None of those were performed.** This work makes the receiver ready to be deployed and tested; it does not make it deployed or tested in production.
