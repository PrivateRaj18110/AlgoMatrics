# monitoring.v1 — controlled staging validation

**Decision: READY FOR PRODUCTION REVIEW.**

Production *review* is requested, not production deployment. Three owner
decisions gate the review itself; they are engineering-complete but not
engineering decisions.

> That review has since been carried out. Its conclusion — including four
> deployment defects this phase could not have found, because it never used the
> deployment artefacts — is in [PRODUCTION_REVIEW.md](PRODUCTION_REVIEW.md), and
> the three decisions are set out in [OWNER_DECISIONS.md](OWNER_DECISIONS.md).
> This document remains the record of what controlled staging proved.

This document covers two phases. The first proved the receiver against real
PostgreSQL, TLS and concurrency, and found seven defects. The second closed the
gaps that phase left open, and found four more.

## 1. Objective

Prove the receiver behaves correctly against the canonical LLS contract under
real staging persistence, transport, concurrency, failure and deployment
conditions — and separate what engineering can settle from what only the owner
can.

Out of scope and not attempted, in either phase: production deployment,
production credentials, live trading, broker integration, strategy changes, LLS
modification, contract redesign.

## 2. Architecture as validated

```
LLS monitoring.v1
    |  HTTPS (staging CA, TLS 1.3)
    v
ops/backend receiver          POST /api/monitoring/v1/messages
    |                          runs as algomatric_receiver — cannot alter evidence
    v
PostgreSQL 17.6               staging cluster, isolated
    |
    +--> evidence (append-only: trigger AND privilege)
    +--> projections (derived, rebuildable)
    |
    v
backend/ platform API         GET /api/v1/operations/monitoring/state
    |                          JWT + session + organisation membership + TRADING_VIEW
    v
frontend/                     /app/lls-monitoring
```

One-way by construction. The receiver contains no HTTP client, imports nothing
from trading or execution, and nothing outside the monitoring path imports it —
each verified by search rather than assumed.

## 3. The input that changed the phase

The previous phase recorded the producer's publication rate as UNKNOWN and named
it the blocker behind capacity, serialisation and retention. **It was specified
in the canonical contract all along:**

> One oldest pending delivery attempt per service cycle; the default cycle
> interval is 30 seconds and minimum is 10.

> A scoped OS delivery-owner lock serializes attempts for each source instance.

The producer is therefore a **serial, single-flight publisher capped at
0.1 msg/s**. The receiver sustains 32.7 msg/s on a single worker — about **327x
headroom** — and the producer never issues a concurrent request.

That one fact resolved three of the eleven blockers. It is also the lesson of
this phase: the missing input was not missing, it was unread.

Arithmetic: `PRODUCTION_CAPACITY_MODEL.md`.

## 4. Results by gate

Legend: `PASS` `PARTIAL` `NOT TESTED` `UNKNOWN` `OWNER DECISION`

### Contract and producer

| Gate | Status | Evidence |
|---|---|---|
| Canonical contract unchanged | PASS | Schema byte-identical to the producer's copy |
| Producer acceptance harness | PASS | **11/11 unmodified**, re-run after every change and under least privilege |
| Content addressing | PASS | Identity recomputed and verified; forged identity refused |
| Negative cases | PASS | 400 / 401 / 403 / 409 / 413 / 422 / 503 each verified |

### PostgreSQL

| Gate | Status | Evidence |
|---|---|---|
| Migration upgrade / downgrade | PASS | Full chain; round-trips; no monitoring drift |
| Persistence, every contract field | PASS | Field by field, including canonical JSON bytes |
| Immutability (ORM, Core, raw SQL) | PASS | All refused; INSERT still allowed |
| Immutability against TRUNCATE | PASS | **Closed this phase** — role separation |
| Duplicate concurrency 2/5/10/20 | PASS | Exactly one acceptance each |
| Sequence concurrency | PASS | Advisory lock; one acceptance per sequence |
| Quarantine | PASS | Separate, admin-only, bytes preserved, bounded |
| Projection and rebuild | PASS | Rebuilt twice, identical, evidence untouched |
| Timestamps canonical | PASS | **Five session timezones**, one rendered value |

### Failure and recovery

| Gate | Status | Evidence |
|---|---|---|
| Database unavailable | PASS | Bounded ~12 s HTTP 503, never a false ACK |
| Database recovery | PASS | Immediate, no duplicates |
| **Persistence interrupted mid-transaction** | **PASS** | **Closed this phase** — 9 checks |
| Storage refuses writes | PASS | Two mechanisms, both 503, clean recovery |
| Literal disk exhaustion (ENOSPC) | **NOT TESTED** | Filling the host volume is unsafe |
| Receiver restart | PASS | Five scenarios, state reconstructed from PostgreSQL |

### Transport and security

| Gate | Status | Evidence |
|---|---|---|
| TLS: valid / expired / mismatch / untrusted | PASS | Each refused distinctly |
| No downgrade; no redirect following | PASS | With a deployment invariant recorded |
| Authentication | PASS | Publisher, admin, agent cross-use, foreign source |
| Hostile input battery | PASS | No leakage, no stack traces, no SQL reaching the database |
| Request bounds (gzip, plain, chunked) | PASS | All terminal 413, bounded memory |
| Logging | PASS | No credentials; no message bodies in the database log |

### Read path and UI

| Gate | Status | Evidence |
|---|---|---|
| Field-by-field trace, producer → API | PASS | Every field preserved |
| Page composition | PASS | 12 assertions against real staging payloads |
| **Browser auth and tenancy** | **PASS** | **Closed this phase** — 8 checks through real JWT, session and membership |
| Monitoring data tenant partitioning | **OWNER DECISION** | Not partitioned — see §6 |

### Deployment and scale

| Gate | Status | Evidence |
|---|---|---|
| Staging isolation | PASS | Separate databases, roles, credentials, port |
| Least-privilege database role | PASS | Verified; harness still 11/11 under it |
| Multi-worker safety | PASS | 14 checks across two processes |
| Performance baseline | PASS | Matrix to concurrency 32, zero errors |
| Sustained load | PASS | 15 minutes — see `PERFORMANCE_BASELINE.md` |
| Resource bounds | PASS | Memory flat, connections capped at pool size |
| Container / orchestration | **NOT TESTED** | No container runtime on this host |
| Remote database | **NOT TESTED** | Single host |
| Production-class hardware | **NOT TESTED** | Developer machine |

### Integrity

| Gate | Status | Evidence |
|---|---|---|
| LLS untouched | PASS | Zero files modified; schema byte-identical |
| Trading isolation | PASS | No control verb; no outbound client; no trading import |
| Retention policy | **OWNER DECISION** | Costed options in `RETENTION_POLICY.md` |

## 5. Defects found and fixed

Eleven across both phases. None was visible from the SQLite suite.

### Phase one

1. **The migration chain could not apply to PostgreSQL at all** — `BOOLEAN DEFAULT 0`. No PostgreSQL deployment of the schema had ever been possible.
2. **Ordered-acceptance race** — concurrent deliveries for one instance raised an unhandled `IntegrityError`. Fixed with a per-instance advisory lock.
3. **Evidence immutable only at the ORM object layer** — Core statements and raw SQL rewrote and deleted it. Fixed with a database trigger.
4. **Unbounded gzip** — 203,910 bytes expanded to 209,715,246 bytes, took 42 s, and wrote a 200 MB database row. Fixed; re-measured at 0 bytes.
5. **A database outage hung requests for over two minutes.** Fixed; bounded 503.
6. **A chunked upload bypassed the new size bound.** Found by re-reading fix 4.
7. **Timestamps rendered in the server's local timezone.**

### Phase two

8. **The evidence table was truncatable by the application's own credential.**
   The append-only trigger does not fire for `TRUNCATE`, and the application
   *owned* the table — so a single statement could empty the forensic record, and
   the privilege cannot be revoked from an owner. Closed by role separation;
   verified; the producer harness still passes 11/11 under the restricted role.
9. **A read-only database and a revoked grant both surfaced as HTTP 500**, not
   the contract's retryable 503, because neither is an `OperationalError`. Every
   database error that prevents the write now maps to 503.
10. **A fresh platform install was impossible.** `0001_baseline.py` builds the
    baseline from live ORM metadata and keeps a hand-maintained list of tables
    belonging to later revisions. Migration `0015` added `workspace_tasks`
    without adding it to that list, so the baseline created the table and `0015`
    then failed with `DuplicateTableError`. Pre-existing, platform, found while
    standing up the authentication test. One-line fix; a fresh database now
    reaches head with 52 tables.
11. **A tooling bug of mine that invalidated two measurements.** The receiver
    stop script killed the launcher process rather than the detached uvicorn
    supervisor that owned the port, so a "restart with one worker" silently left
    a two-worker deployment serving. The per-type storage and sustained-load runs
    were taken against two workers, not one. The script now stops whatever owns
    the port; storage figures are worker-independent and stand; the sustained run
    is labelled with the configuration it actually ran on. Recorded because a
    measurement taken against the wrong configuration is worth more as a
    correction than as a silent fix.

## 6. Findings that are not defects

### Monitoring data is not partitioned by organisation

Verified: a viewer in organisation A and a viewer in organisation B see the
identical projections. Monitoring data is scoped by
`receiver_deployment_environment` only, never by organisation.

Tenancy itself is enforced correctly — presenting another organisation's id is
refused with 403, and membership is checked against the database on every
request. The question is not whether the boundary works, but whether monitoring
data belongs behind one.

If Algomatric operates LLS as one system and organisations are internal teams,
the current behaviour is right: monitoring is infrastructure telemetry. If
organisations are separate customers, then any member with `TRADING_VIEW` can see
the LLS operator's monitoring data.

**Owner decision.** Not something to change silently in either direction.

### `/health` is unauthenticated

The only unauthenticated endpoint. It discloses the deployment tier, schema
versions, database reachability and a quarantine count — low sensitivity, and
useful for an orchestrator probe. It is also the reason the richer metrics §29
asks for (accepted, duplicate and refusal totals, storage growth) should go
behind the administrator token rather than be added here. Currently those totals
are available per publisher instance on `/sources`, which does require a
credential.

## 7. Test inventory

| Suite | Result |
|---|---|
| ops backend (SQLite) | 349 passed, 64 skipped |
| PostgreSQL integration | 35 passed |
| Staging HTTPS | 29 passed |
| Frontend | 137 passed across 27 files |
| TypeScript / ESLint | clean |
| ruff | 274 findings vs 286 at HEAD — none added |
| **Producer acceptance harness** | **11/11, unmodified** |
| Persistence interruption | 9 checks, 0 failed |
| Storage failure | 9 passed, 1 NOT TESTED |
| Browser auth and tenancy | 8 passed, 1 informational |
| Timezone canonicalisation | 4 passed |
| Role separation | 9 passed |
| Multi-worker | 14 passed |
| Failure / recovery driver | 10 passed, 1 NOT TESTED |

## 8. Failure classification

| Item | Classification |
|---|---|
| Defects 1-7 | NEW, found by measurement in phase one; all fixed |
| Defects 8-9 | NEW, found by measurement in phase two; all fixed |
| Defect 10 (platform baseline migration) | **PRE-EXISTING**, platform, found incidentally; fixed |
| Defect 11 (stop script) | NEW, **mine**, in test tooling; fixed and the affected measurements relabelled |
| 3 index drifts in `eod_datasets` / `machines` | **PRE-EXISTING**, unrelated tables, untouched |
| `B008` / `S106` ruff findings | **PRE-EXISTING** — 274 now vs 286 at HEAD |
| `config.py` format drift | **PRE-EXISTING** — drifts at HEAD too |

No test was deleted, skipped or weakened in either phase.

## 9. Remaining NOT TESTED / UNKNOWN

| Item | Why |
|---|---|
| Literal disk exhaustion | Unsafe on this host; the condition it produces is covered |
| Container / orchestration behaviour | No container runtime available |
| Remote database, cross-host networking | Single host |
| Production-class hardware | Developer machine |
| Multi-hour load | 15-minute run; longer not budgeted |
| 408 / 425 / 429 / 502 / 504 | The application emits none of them |
| Production message-type mix | The fixture package is a correctness corpus, not a sample |
| Number of publishing LLS services | Owner input |

## 10. Decision

    READY FOR PRODUCTION REVIEW

Every practical staging gate has been tested. What remains is either physically
unavailable here (containers, a second host, production hardware) or is an owner
decision (retention, tenancy, publisher count) — not engineering work.

See `PRODUCTION_READINESS.md` for the matrix and the three decisions.
