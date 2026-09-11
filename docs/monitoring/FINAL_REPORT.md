# monitoring.v1 receiver — final report

**Date:** 2026-09-11
**Scope:** the algomatric.in receiver and presentation side. The LLS repository was not read, imported, or modified, and no connection to it was created.

---

## IMPLEMENTED

| | |
|---|---|
| Ingress | `POST /api/v1/monitoring/export` on ops-api, public at `/ops/api/v1/monitoring/export` |
| Authentication | upload-only credentials scoped to one `source_id`; separate administrator credential; fail closed |
| Validation | the full contract order — auth, transport size, JSON parse, schema version, JSON Schema, identity, sequence, idempotency/conflict, evidence, projection |
| Evidence | `monitoring_evidence`, append-only, enforced at the ORM |
| Quarantine | distinct from dead-lettering, original request bytes preserved, administrator-only |
| Conflicts | both versions retained, never auto-resolved, surfaced |
| Sequence | gaps recorded and surfaced, never fatal; publisher restart distinguished from loss |
| Projections | derived, rebuildable, deterministic keying, contract ordering |
| Read API | ops-api (9 endpoints) and platform (`/operations/monitoring/*`, 4 endpoints) |
| UNKNOWN | preserved from schema through to rendered pixels |
| STALE | from publisher-supplied horizons, re-evaluated in the browser every second |
| UI | `/app/lls-monitoring` in the authoritative frontend, nine knowledge states rendered distinctly |
| Migration | `a3c7e1d94b62`, seven new tables, additive, reversible |

## TESTED

150 new tests, all passing.

- 61 receiver tests, 46 contract tests (ops backend)
- 11 platform read-path tests
- 32 frontend tests (12 logic, 20 component)
- Full ops backend suite: **330 passed, 0 failed**
- Full frontend suite: **118 passed, 0 failed**; `tsc -b` and `eslint` clean

## VERIFIED

- The dead feed shows `100 / STALE / LAST UPDATE <time>` — not `100 LIVE`, not `0`
- Feed recovery shows A, the outage, and B as three distinguishable facts
- A redelivered `message_id` creates exactly one record, including after ack loss
- Contradictory messages at one entity revision produce a conflict with both sides kept
- A sequence gap is recorded and the message that revealed it is still stored
- Projections rebuild identically from evidence, and the rebuild does not touch evidence
- Evidence rejects both UPDATE and DELETE
- Staging observations never load into a production query
- An unsupported major version is quarantined with its original bytes, and never projected
- Compression cannot smuggle an oversized body past the limit
- No route or contract field reads as a trading control

## FIXED (pre-existing, verified independently)

The four `test_system_health.py` failures reported earlier as pre-existing were **never able to run at all**: `@pytest.mark.asyncio` with no `pytest-asyncio` declared for the ops suite. Determined to be an intended test dependency, declared in `ops/backend/requirements-dev.txt` with `asyncio_mode = auto` in `ops/backend/pytest.ini`. Before: 4 failed, 5 passed. After: 9 passed. No production code changed, no assertion weakened.

One regression was introduced and corrected: `test_release_hotfix.py` pins the exact OpenAPI path set and caught the nine new routes. The new paths were **added** to the expectation; the assertion remains exact equality.

## CORRECTED PLAN

The plan named `ops/frontend` as the UI target. That was wrong, and checking before building is what caught it: `ops/frontend/src/App.tsx` is a redirect shell, and `deploy/nginx/nginx.conf` redirects `/ops` to `/app/dashboard`. Its twenty pages are unreachable. The UI was built in `frontend/` (the authoritative app at `/app/*`) instead; `ops/frontend` was not modified. `ops/backend` **is** live, so the receiver is correctly placed there. Details in `FRONTEND_MONITORING_REPORT.md` §1.

## UNKNOWN

- Behaviour against PostgreSQL — everything ran against SQLite
- Concurrent-publisher racing on the duplicate path
- Throughput, latency, memory, CPU, storage growth — **nothing was measured**
- Rebuild cost at production evidence volume
- Real interoperability with the LLS publisher

## PRE-EXISTING (not caused by this work)

- `test_classification_contract_matches_f9bee1a` — fails on `system_start`/`system_health` kinds from the in-flight system-health work in the working tree
- `test_cross_context_imports_use_public_facades` — `notifications/application/service.py` importing `operations/infrastructure/telemetry_store`, committed code
- `tests/unit/test_operations_api.py` collection error — `tests/` has no `__init__.py` and there is no root `conftest.py`; `PYTHONPATH=.` collects it

## BLOCKED

- **UNKNOWN/STALE on the legacy agent pages.** The `raj_monitor` protocol carries no knowledge-state vocabulary; adding one to the UI would mean inventing states the agent never sent. Those pages can still show a stale agent value as current. Blocked on that protocol, not on this work.
- **Meaningful performance measurement.** Needs a PostgreSQL instance and a synthetic monitoring.v1 generator; neither exists.

## REQUIRES PRODUCTION ACCESS

DNS, TLS, certificate, VM identity, firewall, production secrets, backup/restore execution, restart testing, live ingestion verification. **None were performed, and none were attempted.**

## Open items before staging

1. Confirm the canonical-JSON definition with the LLS side — the most likely silent interoperability break
2. Quarantine retention (unbounded today)
3. Bounded gzip decompression in the shared request middleware
4. Run the migration against PostgreSQL and time it
5. Set `MONITORING_SOURCE_ENVIRONMENTS` so a staging publisher cannot write production rows

---

## Decision

The receiver is complete, internally consistent, and tested to the limits of what a local environment can prove. It has never seen PostgreSQL, a real publisher, or any load. That is precisely the gap a controlled staging integration closes, and it is not a gap that more local testing can close.

**READY FOR CONTROLLED STAGING INTEGRATION**
