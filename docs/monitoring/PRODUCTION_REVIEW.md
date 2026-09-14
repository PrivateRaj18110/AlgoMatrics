# monitoring.v1 — production review and deployment gate

The production review of the Algomatric monitoring.v1 **receiver**. LLS is the
producer and is frozen: this phase modified nothing in the LLS repository, its
monitoring code, or the monitoring.v1 contract, and added no dependency from LLS
to Algomatric.

**Nothing was deployed.** No production infrastructure, DNS, credential,
database, broker or trading path was touched.

---

## Decision

    NO-GO — PRODUCTION DEPLOYMENT BLOCKED

**Updated 2026-09-13, after the owner recorded all four decisions.**

The four decisions are closed. Three of them cost nothing and are done. The
fourth — **organisation-partitioned tenancy** — is not satisfied by this build,
and that converts a previously-open question into a **FAIL**.

| | |
|---|---|
| **Owner decisions** | **All four recorded** (2026-09-13) |
| **Engineering complete** | **No longer.** Decision 3 requires an organisation dimension that does not exist |
| **Approved for production deployment** | **No.** 38 gates, **1 FAIL**, 5 production blockers |

This is not a regression in quality. The receiver is unchanged and still
correct for what it was built to do; the standard it is measured against moved,
by the owner's deliberate choice, and it no longer meets it.

**The single most important consequence:** no production monitoring message may
be accepted until partitioning is complete. `monitoring_evidence` is append-only
behind a database trigger, so a message accepted without organisation
attribution could never be given one. The good news is that **no production
message has ever been accepted**, so there is no unattributable history to
repair — only work to do first.

The engineering position is stronger than at the end of staging. Four defects
that would have broken the *deployment* were found and fixed; the capacity
question that dominated the previous phase turned out to be answerable from the
contract; and the memory question that was left uncharacterised has been
characterised over 4.17 hours and 746,400 messages.

See [OWNER_DECISIONS.md](OWNER_DECISIONS.md) and
[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md).

### What changed this phase

The review began as **inspection only**. Code was modified only where inspection
produced a concrete, evidence-backed engineering requirement — which it did, in
two places: the deployment artefacts, which no previous phase had read, and the
startup guard, which was found to validate one settings object while consulting
another.

| # | Found by inspecting | Severity | Status |
|---|---|---|---|
| 1 | `ops-api.Dockerfile` + `contract.py` | Receiver refuses **every** message; probes still report healthy; failure surfaces as 500 not 503 | **FIXED** |
| 2 | `config.py` startup guard | Half-configured receiver writes evidence under tier `UNKNOWN`, unfixable because evidence is append-only | **FIXED** |
| 3 | `deploy/k8s/45-ops.yaml` | Application runs as the table owner, so its own credential can `TRUNCATE` the forensic record | **FIXED** |
| 4 | `deploy/k8s/45-ops.yaml`, `46-ops-db.yaml` | Memory limit **inside** the measured working range (OOMKill under load); volume under one year at contract maximum | **FIXED** |

Two further defects were found by re-checking my own work, and are recorded
rather than quietly corrected — each is the reason its verification step exists:

* **Introduced by fix 3.** Splitting the new migration Secret out of
  `ops-secrets` moved the agent and dashboard credentials into the wrong
  document, which would have left the application without credentials its own
  startup guard requires. Caught by re-parsing the manifests and asserting their
  invariants.
* **In fix 2 itself.** The guard validated the `Settings` instance it was a
  method of, but asked the process-global settings whether the schema was
  loadable — and did so through an `lru_cache` that could already hold another
  directory's schema. A pure `resolve_schema_dir()` / `schema_problem()` pair
  was split out of the cached path so the guard judges the configuration it is
  actually given. Caught by a regression test that failed for the right reason.

---

## 1. Production review matrix

One row per gate. Each status is exactly one of `PASS` `PARTIAL` `FAIL`
`NOT TESTED` `UNKNOWN` `OWNER DECISION`. No compound statuses.

| # | Gate | Status | Evidence | Classification | Owner decision? | Production blocker? | Next action |
|---|---|---|---|---|---|---|---|
| 1 | Canonical contract | PASS | Schema byte-identical to the producer's handoff copy, sha256 `f94023bc…`; vendored package unmodified | MEASURED | No | No | None |
| 2 | Producer harness | PASS | **11/11 unmodified**, re-run against the final receiver over HTTPS on a clean database | MEASURED | No | No | Re-run against production at deploy (checklist 2.11) |
| 3 | PostgreSQL | PASS | 35 integration tests against PostgreSQL 17.6; migration chain, types, no ORM drift, downgrade/upgrade round-trip | MEASURED | No | No | None |
| 4 | Immutability (row level) | PASS | ORM, Core and raw SQL all refused by trigger `c7f41a92d8e5` | MEASURED | No | No | None |
| 5 | TRUNCATE protection | PASS | Blocked by role separation in staging. A trigger does not fire for TRUNCATE and it cannot be revoked from an owner | MEASURED (staging) | No | No | Apply and verify the grants in production — checklist 2.4 |
| 6 | Sequence | PASS | 1,2,3 → 5 (409) → 4 → 5; a refused sequence leaves no trace | MEASURED | No | No | None |
| 7 | Concurrency | PASS | 2/5/10/20 identical concurrent deliveries → exactly one acceptance; per-instance advisory lock | MEASURED | No | No | None |
| 8 | Quarantine | PASS | Separate, administrator-only, bytes preserved, bounded. 0 rows across 746,400 valid messages | MEASURED | No | No | None |
| 9 | Projection correctness | PASS | All knowledge states preserved; message types separated; keyed as designed | MEASURED | No | No | None |
| 10 | Projection growth behaviour | UNKNOWN | Keyed on `capture_ref`. **Both scenarios MEASURED**: one stable value served 379,200 messages with 1 row; a per-message value grew 1:1. The contract does not say which production does | UNKNOWN | No | No | Ask the producer's owner whether `capture_ref` changes between cycles — a contract clarification, **not** an LLS change |
| 11 | Rebuild | PASS | Twice, identical, evidence unchanged hash-for-hash | MEASURED | No | No | Revisit if a retention option removes evidence — rebuild replays all of it |
| 12 | Restart | PASS | Five scenarios; state reconstructed from PostgreSQL. RSS returns to baseline independent of stored volume | MEASURED | No | No | None |
| 13 | DB outage | PASS | Bounded ~12 s 503, never a false ACK | MEASURED | No | No | None |
| 14 | DB recovery | PASS | Immediate, no duplicates | MEASURED | No | No | None |
| 15 | Persistence interruption | PASS | Transaction destroyed mid-flight; 9 checks | MEASURED | No | No | None |
| 16 | Storage refusal | PASS | Read-only database and revoked grant both → retryable 503, not 500 | MEASURED | No | No | None |
| 17 | ENOSPC | NOT TESTED | No way to exhaust a real volume on this host | NOT TESTED | No | No | Exercise on a disposable volume before or shortly after first deploy |
| 18 | TLS | PASS | Valid / expired / mismatched / untrusted each refused distinctly; producer harness over HTTPS | MEASURED | No | No | Verify the production certificate and hostname — checklist 1.10–1.14 |
| 19 | Authentication | PASS | Publisher, administrator, agent cross-use and foreign-source cases all enforced | MEASURED | No | No | None |
| 20 | Security | PASS | Hostile-input battery; no leakage; bounded bodies; bounded decompression (203,910 B → 209,715,246 B expansion fixed, re-measured at 0 bytes written) | MEASURED | No | No | None |
| 21 | Frontend | PASS | 12 assertions against real staging payloads | MEASURED | No | No | None |
| 22 | Browser auth | PASS | 8 checks through real JWT, session and membership; foreign organisation → 403 | MEASURED | No | No | None |
| 23 | Monitoring tenancy | **FAIL** | **DECIDED 2026-09-13: organisation-partitioned.** The build has no organisation dimension: evidence, audit, quarantine, raw requests and projections have no org column, and all four read endpoints bind the viewer then discard it. The build no longer satisfies the decision | DECIDED — implementation absent | Decided | **Yes — THE blocker** | Implement per `TENANCY_IMPACT_ASSESSMENT.md`. Blocked first on owner input: a `source_id -> organisation` mapping |
| 24 | Publisher count | PASS | **DECIDED 2026-09-13: 1.** Demand 0.1 msg/s = 0.31% of the MEASURED 32.7 msg/s single worker, 327x headroom | DECIDED | Decided | No | None |
| 25 | Throughput | PASS | 32.7 msg/s single worker (matrix), 86.3 msg/s mean over 4.17 h. 327x the contract maximum for one publisher | MEASURED | No | No | None |
| 26 | Request serialisation | PASS | Real and understood — an `async def` endpoint doing blocking I/O — and deliberately unchanged: at 0.1 msg/s single-flight the producer never issues a concurrent request | MEASURED | No | No | Revisit only if the producer's delivery model changes |
| 27 | Memory | PASS | 4.17 h, 746,400 messages, single worker. Plateau reached within ~35,000 messages then flat across 330,000+; **negative** slope over the final 2,000 s of each load phase; 0.01 MB drift over 2,000 s idle; restart returns to baseline. Peak 127.5 MiB | MEASURED | No | No | Linux/container memory accounting remains NOT TESTED — see gate 33 |
| 28 | Retention | PASS | **DECIDED 2026-09-13: evidence INDEFINITE, rejected traffic 30 DAYS.** Rejected-traffic policy implemented and tested; evidence deletion still impossible by design. Volume fills after 3.4-5.9 years at one publisher, so 'indefinite' is a commitment to expand storage | DECIDED | Decided | No | Calendar item: expand the volume before ~year 3.4 |
| 29 | Backup / WAL | PARTIAL | WAL MEASURED as a 0.386 GB steady-state floor (recycled, not growth). Backups, WAL archiving, PITR and replication **NOT MEASURED**. Indefinite evidence retention raises the stakes, and organisation partitioning may add a per-tenant restore requirement | PARTIAL | Policy open | **Yes** | Define a backup policy and size for it — checklist 1.8 |
| 30 | Remote DB | NOT TESTED | Single host; staging PostgreSQL was same-host loopback. Loopback does not represent production network latency and is not offered as such | NOT TESTED | No | **Yes** | Exercise against a networked database before first deploy |
| 31 | Container / orchestration | NOT TESTED | No container runtime on this host. Manifests received **static validation only** — parsed, invariants asserted — which is not runtime validation | NOT TESTED | No | **Yes** | Build and run the image; verify probes, limits and the initContainer ordering |
| 32 | Production hardware | NOT TESTED | Every figure is developer-machine staging performance. Not extrapolated into a guarantee | NOT TESTED | No | No | Re-measure after deploy; headroom is large but unproven on target hardware |
| 33 | Message mix | UNKNOWN | Fixtures are a correctness corpus, not a production sample. Wire sizes span 80x; stored sizes ~2x. Bounds given for both extremes | UNKNOWN | No | No | Observe after deploy |
| 34 | Database role | PASS | Owner runs migrations; the application runs as a non-owning role that cannot DELETE, UPDATE, TRUNCATE or DROP evidence, nor disable the trigger. `REVOKE CONNECT … FROM PUBLIC` templated | MEASURED (staging) | No | No | Verify in production — checklist 2.4 and 2.5 |
| 35 | PostgreSQL logging | PASS | `log_statement=none` and `log_parameter_max_length_on_error=0` pinned in the manifest with the reason; no credential or payload observed in logs | MEASURED | No | No | Confirm on the production instance — checklist 1.7 and 3.7 |
| 36 | X-Forwarded-Proto / edge | PARTIAL | The receiver does not terminate TLS in production and follows no redirects; the trailing-slash invariant is documented. The **production edge configuration** was not available to test | PARTIAL | No | **Yes** | Verify at the edge — checklist 1.11–1.14 |
| 37 | LLS integrity | PASS | Zero files modified under `schemas/` or the handoff package; schema byte-identical; no LLS dependency in requirements; no reverse dependency, shared filesystem, database, memory or process | MEASURED | No | No | None |
| 38 | Trading isolation | PASS | Monitoring exposes one POST (ingest) and six GETs — **no PUT, PATCH or DELETE anywhere**. No outbound HTTP client. No broker/strategy/execution/order/risk/position import. The contract's own rule is *"Never backpressure Core"* | MEASURED | No | No | None |

### Also recorded

These are not gates but were found during the review and are reported rather
than dropped.

| # | Item | Status | Evidence | Classification |
|---|---|---|---|---|
| 39 | Platform baseline migration | PASS | `0001_baseline.py` omitted `workspace_tasks`, so **no fresh platform install was possible**. One-line fix | PRE-EXISTING — platform, not monitoring. Belongs in its own commit and its own review |
| 40 | Load generator keep-alive | PASS | A run reported 200 "errors" the receiver's access log showed never happened — the generator did not reconnect a dropped socket. Fixed; re-run 1,200/1,200 clean | TOOLING DEFECT (mine) |
| 41 | Receiver stop script | PASS | Killed the launcher, not the detached uvicorn supervisor, so a "one worker" run silently served two. Two measurements were retaken | TOOLING DEFECT (mine) |
| 42 | Generator `capture_ref` | PASS | Assigned a unique `capture_ref` per message, inflating projections 1:1 and making earlier throughput a lower bound and storage an upper bound. Mode is now selectable and both were measured | TOOLING DEFECT (mine) |
| 43 | Regression run under load | PASS | A full-suite run overlapping my own PostgreSQL, receiver and load rehearsals reported 2 failures and 1 error in `test_ingest_durability.py`. Both hypotheses tested: 20/20 in isolation, 146/146 with every preceding suite, 354/354 on an idle machine | TOOLING CONTAMINATION (mine) — not a product defect, and not silently ignored |
| 44 | Manifest secret split | PASS | Splitting out `ops-migration-secrets` moved the agent and dashboard credentials into the wrong Secret; the application would have failed its own startup guard. Caught by re-verifying the manifests | Defect introduced and fixed within this phase |
| 45 | Lint findings | PASS | 6 ruff findings in touched files are byte-identical in the committed baseline | PRE-EXISTING — not fixed here, to keep the reviewed diff free of unrelated churn |

## 2. Summary by status

38 gates. Counts computed from the table above, not asserted.

| Status | Gates | Of which production blockers |
|---|---|---|
| PASS | 29 | 0 |
| PARTIAL | 2 | 2 |
| NOT TESTED | 4 | 2 |
| UNKNOWN | 2 | 0 |
| OWNER DECISION | 0 | 0 |
| **FAIL** | **1** | **1** |
| **Total** | **38** | **5** |

The three `OWNER DECISION` rows became two `PASS` (publisher count, retention)
and one **`FAIL`** (tenancy). Blockers fell from seven to five, but the
remaining one is the hardest: it is the only gate that now requires building
something rather than validating it.

**All tested engineering gates passed.** The following owner decisions and
unavailable-infrastructure validations remain:

* **FAIL (1):** organisation-partitioned tenancy is decided but unbuilt. Blocks
  production, and is itself blocked on owner input — a `source_id ->
  organisation` mapping that does not exist.
* **Infrastructure not available to this review (4):** container runtime and
  remote database (both blockers), ENOSPC and production hardware (neither
  blocking, both unclaimed).
* **Partial (2):** backup/WAL policy and the production edge configuration —
  both blockers.
* **Unknown (2):** production `capture_ref` lifecycle and production message
  mix. Neither blocks at one publisher; `capture_ref` is the difference between
  3.4 and 5.9 years of volume.

Nothing is classified `PASS` because it was not observed failing. Every `PASS`
above names the evidence that produced it.

This is deliberately **not** described as "all gates passed".

## 3. The measurement that needed a longer run — resolved

Resident memory rose ~0.45 KB per accepted message across a 15-minute run
without flattening. The previous phase recorded this as PARTIAL and
uncharacterised.

A longer run of the same shape would not have settled it. At a constant rate,
messages and seconds advance together, so "grows per message" and "grows per
second" are indistinguishable. The run was therefore phased — **LOAD-A → IDLE →
LOAD-C → restart**, single worker, 4.17 hours, 746,400 messages — with the two
load phases also differing in `capture_ref` so that projection-driven growth
could be separated from message-driven growth.

### Result

    RESOLVED — the resident set reaches a plateau and stops rising

| Evidence | Finding |
|---|---|
| RSS by tenths of each load phase | Rises during the first tenth, **flat for the remaining nine** — 123.0–123.8 MB across LOAD-A's last 330,000 messages; 116.9–118.6 MB across LOAD-C's last 340,000 |
| Slope over the final 2,000 s | **Negative** in both phases (−0.0093 and −0.0031 KB/msg) |
| r² of the whole-phase linear fit | **0.08 and 0.14** — a straight line explains almost none of the variation, which is why fitting one and quoting its gradient was the wrong reading |
| IDLE, 2,000 s with no traffic | RSS held at **exactly 123.71 MB** — 0.01 MB drift |
| Restart | Returns to **102.75 MB** with 746,400 rows still stored — baseline is independent of stored volume |
| Peak observed | **127.54 MiB**, single worker |

The earlier 0.45 KB/message was the **initial rise, measured in a window too
short to contain anything else.** It is superseded, not contradicted: it
correctly described the first fifteen minutes.

### What is not claimed

That there is no leak of any kind under any workload. This run used one message
type at high rate on Windows; a leak smaller than the ±3 MB oscillation of the
plateau would not be visible, and **Linux and container memory accounting are
NOT TESTED**. The 512Mi limit is headroom against that, not against the
measurement.

### One thing the run overturned

Midway through this phase I hypothesised that the memory growth was driven by
the load generator's per-message `capture_ref` inflating the projection table.
**The full run does not support that**: LOAD-C, with projections bounded, shows a
*higher* nominal per-message slope than LOAD-A, and both are noise at r² < 0.15.
The hypothesis was wrong and is recorded as wrong.

What the `capture_ref` finding *did* establish is real and separate: it changes
**storage** by 1.73× and is an open question for the producer — see gate 10 and
`PRODUCTION_CAPACITY_MODEL.md` §6.

Full methodology, trajectory tables and storage breakdown:
[`PERFORMANCE_BASELINE.md`](PERFORMANCE_BASELINE.md) §7–§8.

---

## 4. Regression evidence

Re-run in full after every change in this phase, on an otherwise idle machine.

Run against the **final** state of the code, after every change in this phase
and again after the owner decisions were implemented (2026-09-13).

| Suite | Result | Notes |
|---|---|---|
| `ops/backend/tests/` (whole suite) | **360 passed, 0 failed, 64 skipped** | Up from 354: six new tests for the decision-2 retention policy. The 64 skips are the integration suites below, which gate on an explicit environment variable |
| `test_monitoring_rejected_retention.py` | **6 passed** | Owner decision 2. Includes a structural assertion that the policy can never name the evidence or audit tables, and a behavioural one that both survive a real prune |
| `test_monitoring_postgres.py` | **35 passed** | Against the live staging PostgreSQL 17.6 |
| `test_monitoring_staging_https.py` | **26 passed, 3 skipped** | Over TLS against the staging receiver; the 3 skips need the deliberately-invalid certificate servers |
| **Producer acceptance harness** | **11/11 passed** | `receiver_acceptance_test.py`, **unmodified** (verified against HEAD), over HTTPS on a clean database |
| `frontend` `MonitoringPage.test.tsx` | **12 passed** | Against real staging payloads, not hand-written mocks |
| `tsc -b` | **clean** | Whole frontend project |
| `eslint src/pages/operations/` | **clean** | |
| `ruff` on every changed file | **no new findings** | Each modified file is at or below its committed baseline count; several improved. New files are clean |
| Alembic heads | **single head** each | `c7f41a92d8e5` (ops), `0015` (platform). No branching |

Nothing was weakened, skipped or deleted to reach this. The only test file
behaviour that changed is the startup-guard test, which was *strengthened*: it
now exercises the guard through the settings object the guard actually reads,
after a design flaw was found in which the guard consulted process-global
settings while validating a local instance.

### One failure that was not a failure

An earlier full-suite run reported 2 failures and 1 error in
`tests/test_ingest_durability.py`, and took 27m22s rather than 6m42s. Those
tests spawn a fresh interpreter per assertion, and the run had overlapped with a
PostgreSQL instance, a receiver, and two load rehearsals on the same machine.

Rather than record the failures or explain them away, both hypotheses were
tested: the file passes 20/20 in isolation, and 146/146 alongside every suite
that precedes it in collection order. Re-run on an idle machine, the whole suite
passes.

Classified **TOOLING DEFECT** — specifically mine, for measuring while the
machine was loaded. It is recorded because a result taken under the wrong
conditions is worth more as a correction than as a silent re-run.

## 5. Changed-file inventory

Six categories. They are separable and **should be committed separately** — in
particular category E, which is not monitoring work at all.

Nothing is committed. No branch was created.

### A — Monitoring product code

| File | Change |
|---|---|
| `ops/backend/app/monitoring/receiver.py` | Per-instance advisory lock; bounded preserved request bytes; every write-preventing database error → retryable 503 |
| `ops/backend/app/api/routers/monitoring.py` | Bounded body read; health reports `databaseReachable` |
| `ops/backend/app/middleware/gzip_request.py` | Bounded decompression; drain-in-place for oversized bodies |
| `ops/backend/app/monitoring/views.py` | Timestamps rendered in UTC, not server-local |
| `ops/backend/app/monitoring/contract.py` | Schema resolution works in the deployed image layout; pure `resolve_schema_dir` / `schema_problem` split out of the cached path |
| `ops/backend/app/database/session.py` | Connect, pool and statement timeouts; keepalives |
| `ops/backend/app/core/config.py` | Production startup guard: refuses to boot half-configured monitoring; timeout settings |

### B — Migrations

| File | Change |
|---|---|
| `ops/backend/alembic/versions/a3c7e1d94b62_…` | `sa.false()` instead of `0` — the chain could not apply to PostgreSQL at all |
| `ops/backend/alembic/versions/c7f41a92d8e5_…` | **New.** Append-only evidence trigger |

Single head (`c7f41a92d8e5`), verified; no branching.

### C — Deployment artefacts

| File | Change |
|---|---|
| `deploy/docker/ops-api.Dockerfile` | Ship the canonical schema into the image |
| `deploy/k8s/45-ops.yaml` | `MONITORING_*` templated; owner/receiver role split; memory justification corrected to the single-worker measurement |
| `deploy/k8s/46-ops-db.yaml` | Volume sized from measurement with both projection scenarios; logging pinned; role bootstrap documented |
| `deploy/compose/docker-compose.yml` | Same `MONITORING_*` shape, for parity |
| `.env.example` | The four `MONITORING_*` settings, with the half-configured warning |

**Statically validated only** — parsed, invariants asserted. Never applied.

### D — Tests and tooling

| File | Change |
|---|---|
| `ops/backend/tests/test_production_safety.py` | 5 startup-guard regressions |
| `ops/backend/tests/test_monitoring_receiver.py` | Extended |
| `ops/backend/tests/test_monitoring_postgres.py` | **New** — real-PostgreSQL suite (35 tests) |
| `ops/backend/tests/test_monitoring_staging_https.py` | **New** — HTTPS delivery (26 tests) |
| `ops/backend/tests/test_request_decompression_bounds.py` | **New** |
| `frontend/…/MonitoringPage.test.tsx`, `__fixtures__/` | **New** — 12 assertions against real staging payloads |
| `ops/backend/tools/monitoring_loadgen.py` | **New** — synthetic load, marked as synthetic in every message, with selectable `capture_ref` mode |
| `ops/backend/scripts/monitoring_capacity_table.py` | **New** — reproduces the capacity tables |

### E — Not monitoring work

| File | Change |
|---|---|
| `backend/migrations/versions/0001_baseline.py` | `workspace_tasks` added to the later-revision list. **Pre-existing platform bug: no fresh install was possible.** Unrelated to monitoring; **its own commit and its own review** |

### F — Documentation

New: `PRODUCTION_REVIEW.md`, `OWNER_DECISIONS.md`, `DEPLOYMENT_CHECKLIST.md`,
`PRODUCTION_CAPACITY_MODEL.md`, `PERFORMANCE_BASELINE.md`, `RETENTION_POLICY.md`,
`DEPLOYMENT_VALIDATION.md`, `FAILURE_RECOVERY.md`, `POSTGRESQL_VALIDATION.md`,
`TLS_VALIDATION.md`, `STAGING_VALIDATION.md`.

Modified: `README.md`, `PRODUCTION_READINESS.md` (superseded banner),
`CONTRACT_IMPLEMENTATION_REPORT.md` and
`superseded/monitoring-export-v1-proposal/DATA_CONTRACT.md` (broken links
repaired after the proposal was archived).

### Not changed, and verified not changed

`schemas/monitoring-v1/**` and `tests/fixtures/lls-monitoring-v1-handoff/**` —
zero files modified, schema byte-identical to the producer's copy.

## 6. What is explicitly not claimed

* That the receiver has run in a container, on Linux, on production hardware, or
  against a networked database. Each is `NOT TESTED` and is not extrapolated
  from the measurements that were taken.
* That the production message mix resembles the fixture package. The fixtures
  are a correctness corpus; the mix is `UNKNOWN` and bounds are given for both
  extremes instead.
* That any publisher count is likely. The per-publisher rate is a contract fact;
  the count is an owner input and is not inferred.
* That retention is legally or operationally unconstrained. Obligations outside
  this team are `UNKNOWN` and cannot be inferred from the code.
* That the manifests are correct because they parse. They received **static
  validation only** — parsed, invariants asserted. That is not runtime
  validation, and they have never been applied to a cluster.
* That projection storage is bounded. It is bounded **under a stable
  `capture_ref`**, which was MEASURED; production behaviour is `UNKNOWN`.
* That memory is leak-free under every workload. The plateau is MEASURED on
  Windows with one message type; a leak below the ±3 MB plateau oscillation
  would not be visible, and Linux/container accounting is `NOT TESTED`.
* That the capacity model is a disk-capacity model. It covers database growth.
  Backups, WAL archiving, PITR and replication are `NOT MEASURED`.

---

## 7. What must happen before deployment

Seven production blockers, none of them engineering work on the receiver.

### Owner decisions (3)

1. **Retention** — accepted evidence, and rejected traffic. The second is the
   unbounded one and can be answered alone.
2. **Monitoring tenancy** — operator-wide or organisation-partitioned. Partly
   irreversible once production traffic is accepted, because evidence is
   append-only.
3. **Publisher count** — an integer. It sets the volume size and determines
   whether the retention answer is still the one the owner would give.

### Validations needing infrastructure this review did not have (2)

4. **Container runtime** — build and run the image; verify probes, limits and
   initContainer ordering. Static manifest validation is not this.
5. **Networked database** — everything measured here is same-host loopback.

### Policy and edge configuration (2)

6. **Backup policy** — undefined and unmeasured. The capacity model does not
   include it.
7. **Production edge** — TLS termination, hostname validation,
   `X-Forwarded-Proto`, and no downgrade path.

Then work through [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) in order.
Steps 2.3 and 2.4 are the ones that make the append-only guarantee real in
production rather than in staging.

### Worth asking the producer, but not a blocker

Does `capture_ref` change between service cycles? It decides a 1.73× difference
in storage per message. A contract clarification — **not** an LLS change.
