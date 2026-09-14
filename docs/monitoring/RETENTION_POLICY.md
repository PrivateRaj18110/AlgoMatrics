# monitoring.v1 — retention policy

## Status

    ACCEPTED EVIDENCE   = INDEFINITE        (owner decision 1, 2026-09-13)
    REJECTED TRAFFIC    = 30 DAYS           (owner decision 2, 2026-09-13)
    DECIDED BY          = the authorised project owner
    RECORDED BY         = engineering, from the owner's explicit selection

## The decisions

### Decision 1 — accepted evidence: retained indefinitely

Nothing deletes accepted evidence, and **nothing may be added that does**.

| | |
|---|---|
| Effect on storage | 18.2 GB/year at one publisher, contract maximum rate, Scenario A. See §3 |
| Effect on rebuild | **None.** `projections.rebuild()` replays all evidence and continues to reconstruct the same state, because no evidence is ever removed. This is the option that leaves rebuild semantics untouched |
| Effect on append-only protection | **None — it is preserved in full.** Trigger `c7f41a92d8e5` stays, role separation stays. No TTL, cron, cascade or archive job may target `monitoring_evidence` |
| Engineering required | **None.** No migration, no trigger change, no job |

Rationale as recorded: at one publisher (decision 4) the growth is bounded and
affordable, and indefinite retention preserves the forensic record the system
exists to hold.

### Decision 2 — rejected traffic: 30 days

`monitoring_quarantine` and `monitoring_raw_requests` only.

| | |
|---|---|
| Effect on storage | Bounds the one growth path a holder of a valid publisher credential could drive deliberately — malformed or oversized uploads cost storage on the refusal path |
| Effect on rebuild | **None.** Rejected traffic is not evidence and is never replayed |
| Effect on append-only protection | **None.** The trigger is scoped to `monitoring_evidence`; these two tables were always mutable, by design |
| Engineering required | A bounded scheduled cleanup — implemented, see below |

**Explicitly out of scope, and the omissions are the point:**

* `monitoring_evidence` — decision 1 is indefinite.
* `monitoring_audit` — the security record of *every* attempt, accepted and
  rejected alike. It is not "rejected traffic"; pruning it would erase the record
  that a refusal ever happened.
* `monitoring_projections`, `monitoring_sequence_state` — derived and
  per-instance state, not traffic.

**Implementation.** `app/services/retention_service.py`, policies
`monitoring.quarantine` and `monitoring.raw_requests`. Both share one cutoff so a
quarantine row and the raw body it describes age out together, never leaving half
a forensic record. Dry-run supported, as with every other policy in that module.

The application default is **0 (disabled)**. The 30-day value is asserted in
deployment configuration (`MONITORING_REJECTED_RETENTION_DAYS: "30"` in
`deploy/k8s/45-ops.yaml`), so no other environment deletes anything it was not
explicitly told to. Covered by `tests/test_monitoring_rejected_retention.py`,
including a structural assertion that the policy can never name the evidence or
audit tables.

## 1. What changed since the last phase

| | Previous phase | Now |
|---|---|---|
| Publication rate | UNKNOWN — named the blocking input | **CONTRACT: 0.1 msg/s maximum**, single-flight |
| Growth | "unbounded", no horizon | **18.2 GB/year** (Scenario A) or **31.2 GB/year** (Scenario B) at the contract maximum, one publisher |
| Refused traffic amplification | 233 MB written by 27 refusals | fixed; re-measured at **0 bytes** |
| Evidence deletion | blocked by trigger | unchanged; role separation additionally blocks TRUNCATE, MEASURED in staging and templated for production in `deploy/k8s/45-ops.yaml` but NOT YET APPLIED to any production database |

Growth is still technically unbounded — nothing deletes anything — but the
*rate* of that growth is now a contract fact rather than an open question.

## 2. Measured growth

**MEASURED** over 750,400 stored messages on PostgreSQL 17.6 (large-n; these
supersede the earlier n=3,200 figures).

| Table | Per row | Bounded? |
|---|---|---|
| `monitoring_evidence` | **5,505 bytes** (12 kB snapshot, TOAST-compressed) | no — grows per accepted message |
| `monitoring_audit` | **269 bytes** | no — grows per ingest attempt |
| `monitoring_projections` | **4,128 bytes per projection row** | **UNKNOWN** — depends on the production `capture_ref` lifecycle |
| `monitoring_sequence_state` | one row per publisher instance | **yes** |
| `monitoring_quarantine` | per refused message | no, but bounded per row |
| `monitoring_raw_requests` | capped at 1 MiB + 64 KiB per row | no, but bounded per row |

Projection growth was previously recorded here as bounded without
qualification. It is not established. Both scenarios were MEASURED — one stable
`capture_ref` served 379,200 messages with a single projection row; a
per-message `capture_ref` grew the table 1:1 — and the contract does not say
which production does. See `PRODUCTION_CAPACITY_MODEL.md` §6.

## 3. Storage projections

At the contract maximum rate (0.1 msg/s), **one publisher**, all-snapshot mix,
nothing deleted. DERIVED from the measured bytes above.

| Horizon | Evidence | + audit | **Scenario A total** | **Scenario B total** |
|---|---|---|---|---|
| 1 month | 1.43 GB | 0.07 GB | **1.5 GB** | **2.6 GB** |
| 1 year | 17.4 GB | 0.8 GB | **18.2 GB** | **31.2 GB** |
| 3 years | 52.1 GB | 2.5 GB | **54.6 GB** | **93.7 GB** |
| 7 years | 121.5 GB | 5.9 GB | **127.4 GB** | **218.6 GB** |

Scenario A = projections bounded. Scenario B = projections grow 1:1 with
evidence. At the contract **default** rate (0.033 msg/s), divide by three.

Three multipliers, all **UNKNOWN**, and none of them inferred here: the number
of publishing LLS services, the production message mix, and the `capture_ref`
lifecycle. The full publisher-count table is in
`PRODUCTION_CAPACITY_MODEL.md` §8.

**These figures are database growth only.** WAL has a MEASURED steady-state
floor of 0.386 GB; backups, WAL archiving, PITR and replication are NOT
MEASURED and are not included.

## 4. The options

### Option A — evidence kept indefinitely; bound only the rejected traffic

Retain all accepted evidence. Age out `monitoring_raw_requests` and
`monitoring_quarantine` after a fixed window. Optionally age out
`monitoring_audit`.

| | |
|---|---|
| Storage, 7 years | ~130 GB at the contract maximum; ~43 GB at the default rate |
| Forensic reconstruction | **complete, permanently** |
| Rebuild | unaffected — `projections.rebuild()` keeps working from full evidence |
| Quarantine | bounded |
| Migration required | none for evidence; the append-only trigger is untouched |
| Operational complexity | **lowest** — one scheduled job over two tables |

*The case for it:* at these volumes, keeping everything is affordable. A
forensic evidence store that can explain any past trading observation is the
system's entire purpose, and 130 GB over seven years is not a reason to
compromise it. The tables that genuinely need bounding are the ones holding
traffic the receiver *rejected*, whose value decays in days.

### Option B — archive evidence after a defined period

As A, plus: export evidence older than *N* months to object storage as canonical
JSON with its digest, then remove it from the hot table.

| | |
|---|---|
| Storage, hot table | bounded at *N* months |
| Forensic reconstruction | complete, but requires retrieving the archive |
| Rebuild | **constrained** — `projections.rebuild()` replays *all* evidence; it would become partial, or would have to read the archive |
| Migration required | yes — the append-only trigger must be dropped in a reviewed migration |
| Operational complexity | **high** — archive format, integrity verification, restore path, and a rebuild that spans two stores |

*The case against it, at these volumes:* it buys a bounded hot table at the cost
of the rebuild guarantee and a whole archival subsystem, to solve a growth
problem that is ~18 GB/year.

### Option C — staging unlimited; production requires an approved policy

Keep the present behaviour (nothing deleted) as the explicit staging position,
and make an approved retention policy a named prerequisite of production
sign-off rather than something inherited by default.

| | |
|---|---|
| Storage | unbounded, but at a known and modest rate |
| Forensic reconstruction | complete |
| Rebuild | unaffected |
| Migration required | none |
| Operational complexity | none now; defers the decision |

*The case for it:* it is honest about where the system is, and it is what is
already true. Its weakness is that "decide later" has a way of becoming "never
decided".

### A note on tiering by message type

Considered and **recommended against**. Retaining `monitoring.incidents` longer
than `monitoring.snapshot` would mean the receiver deciding which of the
producer's observations matter. That is the producer's judgement, not ours, and
encoding it here would be exactly the kind of reinterpretation the whole
contract implementation has avoided.

## 5. Accepted vs rejected retention should differ

They should, and by a lot:

* **Accepted evidence** is the record the system exists to hold. Its value does
  not decay; an observation from a year ago is what explains a trading outcome
  from a year ago.
* **Rejected raw bodies and quarantine rows** are diagnostic material. Their
  value is measured in days to weeks — nobody investigates a malformed request
  from last year — and they are the tables an attacker with a valid credential
  could otherwise grow.

Any policy treating them the same is either hoarding junk or discarding
evidence.

## 6. What any deletion policy must deal with

* **The append-only trigger.** Migration `c7f41a92d8e5` blocks row-level DELETE
  on `monitoring_evidence`. Any evidence-deleting job must drop it in its own
  reviewed migration — deliberately, so that deleting evidence is a visible act
  rather than a configuration flag.
* **Role separation.** The receiver's own credential cannot delete or truncate
  evidence (see `DEPLOYMENT_VALIDATION.md`). A retention job needs the owner
  role, which is a second deliberate step.
* **Rebuild.** `projections.rebuild()` replays *all* evidence. Any option that
  removes evidence from the hot table changes what rebuild means, and that has
  to be decided with the policy rather than discovered afterwards.
* **Legal and operational obligations.** UNKNOWN to this phase. If monitoring
  evidence is ever used to explain a trading outcome to anyone outside the team,
  its retention may be governed by rules nobody here has stated.

## 7. What is being asked of the owner

Two questions, in order:

1. **How long must accepted monitoring evidence remain directly queryable?**
   If the answer is "indefinitely, at these volumes" then Option A closes this
   gate with a small scheduled job and no migration.
2. **What retention applies to rejected traffic** — quarantine and raw request
   bodies? A fixed window (30 / 60 / 90 days) is sufficient; the only wrong
   answer is the current one, which is "forever".

Answering (2) alone would close the unbounded-growth concern for the tables that
actually warrant it, and can be done independently of (1).

## 8. Status summary

    ACCEPTED EVIDENCE           = INDEFINITE (owner decision 1, 2026-09-13)
    REJECTED TRAFFIC            = 30 DAYS    (owner decision 2, 2026-09-13)
    PUBLISHER COUNT             = 1          (owner decision 4, 2026-09-13)
    GROWTH RATE                 = MEASURED + CONTRACT: 18.2 GB/yr (scenario A)
                                  or 31.2 GB/yr (scenario B), one publisher
    STILL UNBOUNDED BY DESIGN   = evidence (indefinite, by decision), audit
    NOW BOUNDED                 = quarantine, raw_requests (30 days)
    REFUSAL AMPLIFICATION       = fixed, re-measured at zero
    EVIDENCE DELETION           = blocked by trigger everywhere;
                                  TRUNCATE additionally blocked by role
                                  separation, MEASURED in staging only
                                  (production grants are a deployment step)
    AUDIT TABLE                 = deliberately NOT pruned; it is the record of
                                  every attempt, not rejected traffic
