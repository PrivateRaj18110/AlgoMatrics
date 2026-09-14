# monitoring.v1 — production capacity model

Companion to `PERFORMANCE_BASELINE.md` and `RETENTION_POLICY.md`.

Every figure is labelled **MEASURED**, **CONTRACT**, **DERIVED** or **UNKNOWN**.
Nothing here is an estimate dressed as a fact.

## 1. The input that was missing — and was not actually missing

The previous phase recorded the producer's publication rate as UNKNOWN and named
it the blocker behind every capacity question. That was wrong, and the correction
matters more than anything else in this document.

**The rate is specified in the canonical contract.** It was in
`schemas/monitoring-v1/ALGOMATRIC_MONITORING_CONTRACT.md` the whole time:

> One oldest pending delivery attempt per service cycle; the default cycle
> interval is 30 seconds and minimum is 10.

and, in the transport section:

> A scoped OS delivery-owner lock serializes attempts for each source instance
> without holding the evidence writer lock during network activity.

So the producer is a **serial, single-flight publisher with a floor on its
interval**. It does not burst, it does not parallelise, and it cannot be
configured below a 10-second cycle.

| Property | Value | Source |
|---|---|---|
| Delivery model | one pending message per service cycle | CONTRACT |
| Default cycle | 30 s | CONTRACT |
| Minimum cycle | 10 s | CONTRACT |
| **Maximum sustained rate** | **0.1 msg/s** | CONTRACT (derived from the 10 s floor) |
| Default rate | 0.033 msg/s | CONTRACT |
| Concurrent in-flight deliveries per service | 1 | CONTRACT |
| Outbox depth | 256 messages | CONTRACT |
| Max attempts per message | 100 | CONTRACT |
| Burst above the cycle rate | none — backlog still drains one per cycle | CONTRACT |

One caveat, stated rather than glossed: this is the rate of **one LLS monitoring
service**. If several LLS deployments ever publish to one receiver, the receiver
sees the sum. How many services will exist in production is **UNKNOWN** and is
an owner input — but the per-service ceiling is now a contract fact, so the
question has changed from "what is the rate?" to "how many publishers?".

## 2. Rate arithmetic

| Rate | msg/s | per day | per month | per year |
|---|---|---|---|---|
| Contract maximum (10 s cycle) | 0.1000 | 8,640 | 259,200 | 3,153,600 |
| Contract default (30 s cycle) | 0.0333 | 2,880 | 86,400 | 1,051,200 |

Applied to publisher counts and per-message storage in §8.

## 3. Headroom against the measured receiver

| | Value | Source |
|---|---|---|
| Receiver throughput, 1 publisher, 1 worker | 32.7 msg/s | MEASURED |
| Receiver throughput, peak (16 publishers) | 66.3 msg/s | MEASURED |
| Producer maximum demand | 0.1 msg/s | CONTRACT |
| **Headroom at the single-publisher figure** | **327x** | DERIVED |

This reframes the "request serialisation" blocker completely. The receiver
serialises requests because an `async def` endpoint performs blocking database
I/O — that finding stands, and it is still the right thing to fix eventually.
But it was recorded as a production blocker on the assumption that throughput
might matter. Against a contract-capped 0.1 msg/s single-flight publisher, a
receiver that sustains 32.7 msg/s on one worker has roughly **327 times** the
capacity it needs, and the producer never issues a second concurrent request
anyway.

See `PERFORMANCE_BASELINE.md` §3 for the decision this leads to.

## 4. Message sizes

**MEASURED**, from the producer's own fixtures:

| Message type | Fixtures | Median wire size |
|---|---|---|
| `monitoring.events` | 7 | 98,291 bytes |
| `monitoring.snapshot` | 9 | 11,926 bytes |
| `monitoring.incidents` | 3 | 1,934 bytes |
| `monitoring.forensic_reference` | 2 | 1,218 bytes |

Range: 1.2 kB to 98 kB, an ~80x spread. Overall median 11.9 kB. Stored size compresses that spread to roughly 2x — see `PERFORMANCE_BASELINE.md` §5.

The **mix** is `UNKNOWN`. The fixture package is a correctness corpus, not a
production sample, and §6 of this phase's brief is explicit that production rates
must not be inferred from it. Counts above describe the test package only.

Because the spread is 80x, a capacity figure quoted without a mix is close to
meaningless. The bounds below are therefore given for the two extremes.

## 5. Storage per message

**MEASURED** on PostgreSQL 17.6 over **750,400 stored messages**. These
supersede the earlier n=3,200 and n=120 figures, in which fixed page and index
costs had not yet amortised away.

| Table | Heap | Indexes | Total (incl. TOAST) | Bytes per message |
|---|---|---|---|---|
| `monitoring_evidence` | 768.5 MB | 254.3 MB | 4,131.2 MB | **5,505** |
| `monitoring_audit` | 161.8 MB | 40.0 MB | 201.9 MB | **269** |
| `monitoring_projections` | 329.6 MB | 74.4 MB | 1,513.7 MB | **4,128 per projection row** |
| `monitoring_sequence_state` | 1.1 MB | 15.6 MB | 16.8 MB | bounded by instance count |
| `monitoring_quarantine` | — | — | 0 | 0 (no refusals in the run) |
| `monitoring_raw_requests` | — | — | 0 | 0 (no refusals in the run) |

## 6. Projection growth — two scenarios, and the contract does not choose

An earlier version of this document stated that `monitoring_projections` "does
not grow per message". **That was not established and has been corrected.** The
difference between the two readings is the difference between a bounded table
and a second unbounded one.

A projection is keyed by
`(receiver_deployment_environment, source_id, message_type, capture_ref)`.
Whether the table is bounded therefore depends entirely on how `capture_ref`
behaves in production. The contract says only that page offsets are *"tied to an
immutable capture and projection version"*, which is consistent with either
reading.

**Both were MEASURED**, ~370,000 messages each, in the same run:

| | `capture_ref` | Projection rows added | Evidence growth | **Whole-database growth** |
|---|---|---|---|---|
| **Scenario A** | one stable value | **0** for 379,200 messages | 5,468 B/msg | **5,759 B/msg** |
| **Scenario B** | new value per message | **+366,400** for 366,400 messages | 5,544 B/msg | **9,962 B/msg** |

One projection row served all 379,200 Scenario A messages. The evidence cost is
identical either way — the entire difference is the projection table and its
unique index.

**Scenario B costs 1.73× Scenario A per message.**

### Which applies in production is UNKNOWN

Every message in the producer's fixture package carries the same `capture_ref`
(`historical-final`), which points at Scenario A. But the fixture package is a
correctness corpus, not a production sample, and this document does not infer
production behaviour from it.

    PRODUCTION capture_ref LIFECYCLE = UNKNOWN

So **projection storage must not be described as universally bounded** until the
producer contract or observed production behaviour establishes it. Both
scenarios are carried through every table below. Neither is chosen here, and
neither is more likely than the other on the evidence available.

If this matters enough to the volume sizing — and §8 shows it can — the question
to put to the producer's owner is narrow: *does `capture_ref` change between
service cycles?* It is a contract clarification, not an LLS change.

## 7. Per-message database cost

DERIVED from the MEASURED figures in §5, for the two scenarios in §6:

    Scenario A   5,505 + 269               =  5,774 bytes/message
    Scenario B   5,505 + 269 + 4,128       =  9,902 bytes/message

## 8. Capacity by publisher count

Publisher count is an **owner input** and is not decided here. This table gives
the consequence of each candidate so the decision can be made against arithmetic
rather than intuition.

Reproduce with `python -m scripts.monitoring_capacity_table` from `ops/backend`.
Every cell is computed; none is typed by hand.

### Throughput — demand against the MEASURED receiver

| Publishers | Demand at contract max | Messages/day | Messages/year | % of 32.7 msg/s | Headroom |
|---|---|---|---|---|---|
| 1 | 0.1 msg/s | 8,640 | 3,153,600 | 0.31% | 327x |
| 5 | 0.5 msg/s | 43,200 | 15,768,000 | 1.53% | 65x |
| 10 | 1.0 msg/s | 86,400 | 31,536,000 | 3.06% | 33x |
| 25 | 2.5 msg/s | 216,000 | 78,840,000 | 7.65% | 13x |
| 50 | 5.0 msg/s | 432,000 | 157,680,000 | 15.29% | 7x |
| 100 | 10.0 msg/s | 864,000 | 315,360,000 | 30.58% | 3x |

DERIVED: demand reaches the measured single-worker throughput at **327
publishers**. No plausible publisher count makes throughput the binding
constraint.

### Storage, GB/year at the contract MAXIMUM rate, nothing deleted

| Publishers | Evidence | Audit | **Scenario A total** | Projections (B only) | **Scenario B total** |
|---|---|---|---|---|---|
| 1 | 17.4 | 0.8 | **18.2** | 13.0 | **31.2** |
| 5 | 86.8 | 4.2 | **91.0** | 65.1 | **156.1** |
| 10 | 173.6 | 8.5 | **182.1** | 130.2 | **312.3** |
| 25 | 434.0 | 21.2 | **455.2** | 325.5 | **780.7** |
| 50 | 868.0 | 42.4 | **910.4** | 650.9 | **1,561.3** |
| 100 | 1,736.1 | 84.8 | **1,820.9** | 1,301.8 | **3,122.7** |

### Storage, GB/year at the contract DEFAULT rate (30 s cycle)

| Publishers | Scenario A total | Scenario B total |
|---|---|---|
| 1 | 6.1 | 10.4 |
| 5 | 30.3 | 52.0 |
| 10 | 60.7 | 104.1 |
| 25 | 151.7 | 260.2 |
| 50 | 303.5 | 520.4 |
| 100 | 607.0 | 1,040.9 |

### How long the provisioned 100Gi volume lasts

107.4 GB provisioned, less the **MEASURED** 0.386 GB steady-state WAL floor =
107.0 GB usable. Backups, WAL archiving, PITR and replication are **NOT
MEASURED** and are *not* subtracted, so **every figure below is an upper bound
on the time actually available.**

| Publishers | Scenario A, max rate | Scenario B, max rate | Scenario A, default rate |
|---|---|---|---|
| 1 | 5.88 yr | 3.43 yr | 17.63 yr |
| 5 | **1.18 yr** | **0.69 yr** | 3.53 yr |
| 10 | 0.59 yr | 0.34 yr | 1.76 yr |
| 25 | 0.24 yr | 0.14 yr | 0.71 yr |
| 50 | 0.12 yr | 0.07 yr | 0.35 yr |
| 100 | 0.06 yr | 0.03 yr | 0.18 yr |

### The conclusion this forces

**Storage is the binding constraint, not throughput, and it binds far earlier
than the throughput headroom suggests.**

The 327× figure in §3 is accurate but answers the wrong question. The volume
provisioned in `deploy/k8s/46-ops-db.yaml` is sized for **one** publisher at the
contract maximum with nothing deleted. It falls below one year of capacity at
**6 publishers** under Scenario A, and at **4 publishers** under Scenario B.

An earlier note in this phase said "inside 18 months at five publishers". The
verified arithmetic is **1.18 years (about 14 months)** under Scenario A and
**0.69 years (about 8 months)** under Scenario B. The earlier figure was
optimistic and is corrected here.

Three consequences, all owner decisions rather than engineering ones:

* The publisher count must be known before the volume size is final. It is
  **UNKNOWN**.
* Beyond roughly two publishers, "keep everything forever" stops being cheap.
  The retention decision is therefore a function of the publisher count, not
  independent of it.
* The `capture_ref` question changes the answer by 1.73×. It is a contract
  clarification worth asking the producer's owner for — **not** an LLS change.

### What this model does NOT include

| Component | Status |
|---|---|
| Evidence, audit, projections, sequence state, indexes, TOAST | MEASURED |
| WAL steady-state floor | MEASURED (0.386 GB; recycled, not growth) |
| Backups | **NOT MEASURED** |
| WAL archiving / PITR | **NOT MEASURED** |
| Replication | **NOT MEASURED** |
| Long-horizon autovacuum bloat | **NOT MEASURED** |
| Filesystem overhead and reserved blocks | **NOT MEASURED** |

This is a **database growth model, not a full disk-capacity model.** It must not
be quoted as the latter.

## 9. Capacity under the decided parameters

Owner decisions recorded 2026-09-13: **1 publisher**, **indefinite** evidence
retention, **30 days** rejected traffic. This section replaces the scenario
sweep in §8 with the single case that now applies.

| Input | Value | Label |
|---|---|---|
| Publishers | 1 | **OWNER DECISION** |
| Evidence retention | indefinite | **OWNER DECISION** |
| Rejected-traffic retention | 30 days | **OWNER DECISION** |
| Rate per publisher | 0.1 msg/s max | CONTRACT |
| Evidence per message | 5,505 B | MEASURED (n=750,400) |
| Audit per message | 269 B | MEASURED |
| Projection row | 4,128 B | MEASURED |
| `capture_ref` lifecycle | — | **UNKNOWN** |

**Demand** — CALCULATED from the contract rate, not measured:

    0.1 msg/s        8,640 messages/day        3,153,600 messages/year
    0.31% of the MEASURED 32.7 msg/s single-worker throughput (327x headroom)

**Storage** — CALCULATED from measured per-message bytes:

| | Per message | Per year | 1 yr | 3 yr | 7 yr |
|---|---|---|---|---|---|
| Scenario A (projections bounded) | 5,774 B | 18.2 GB | 18.2 GB | 54.6 GB | 127.5 GB |
| Scenario B (projections 1:1) | 9,902 B | 31.2 GB | 31.2 GB | 93.7 GB | 218.6 GB |

Rejected traffic contributes nothing to the long-horizon figure: at 30 days it
reaches a steady state rather than accumulating, and across the entire 746,400
message characterisation run it was **0 rows** — the receiver refused nothing.

### The tension the owner should see

**Indefinite retention on a finite volume means the volume will fill.** That is
not a contradiction in the decision — it is the consequence of it, and at one
publisher the runway is long:

    Scenario A    100Gi (107.0 GB usable) exhausted after   5.88 years
    Scenario B    100Gi (107.0 GB usable) exhausted after   3.43 years

"Indefinite" is therefore a commitment to **grow storage before then**, not a
statement that storage is unbounded. Two consequences:

* The volume must be expanded, or migrated to a managed instance that can be
  expanded, before roughly year 3.4 (the conservative scenario). This is an
  operational calendar item, not an engineering unknown.
* The storage alert in the deployment checklist must fire on *projected
  exhaustion against the retention horizon*, not on a raw percentage — because
  with indefinite retention there is no point at which usage stops rising.

The `capture_ref` clarification is what separates 3.43 from 5.88 years. It
remains **UNKNOWN** and is worth asking the producer's owner, but at one
publisher it does not block: even the pessimistic reading leaves over three
years.

### What this still excludes

Backups, WAL archiving, PITR and replication remain **NOT MEASURED** and are not
subtracted from the 107.0 GB. The figures above are therefore **upper bounds on
the time available**, and a backup policy will shorten them.

## 10. What remains UNKNOWN

| Input | Status | Why it matters |
|---|---|---|
| Number of publishing LLS services in production | **DECIDED: 1** (2026-09-13) | See §9 for the resulting capacity |
| Production message-type mix | UNKNOWN | 80x spread in wire size; ~2x in stored size |
| `capture_ref` lifecycle in production | UNKNOWN | Decides Scenario A vs B — a **1.73x** difference in storage per message. See §6 |
| Backups, WAL archiving, PITR, replication | NOT MEASURED | §8 is a database growth model, not a disk-capacity model |
| Required evidence retention period | **DECIDED: indefinite** (2026-09-13) | See `RETENTION_POLICY.md`; the volume fills after 3.4-5.9 years |
| Production hardware | NOT TESTED | Every figure here is developer-machine staging. Throughput headroom is 327x at one publisher, so CPU is unlikely to bind; disk capacity is the constraint that does |
| Backup and WAL overhead | NOT MEASURED | Adds to the storage figures above |

## 11. Status

    PUBLICATION RATE     = CONTRACT-SPECIFIED (0.1 msg/s maximum, single-flight)
    THROUGHPUT HEADROOM  = 327x, DERIVED from a MEASURED 32.7 msg/s
    MESSAGE SIZES        = MEASURED (1.2 kB - 98 kB)
    MESSAGE MIX          = UNKNOWN
    PUBLISHER COUNT      = 1 (owner decision, 2026-09-13)
    STORAGE GROWTH       = DERIVED from measured bytes and contract rate
    PROJECTION GROWTH    = TWO SCENARIOS; production behaviour UNKNOWN
    BINDING CONSTRAINT   = STORAGE, not throughput (see §8)
    BACKUP / WAL ARCHIVE = NOT MEASURED
    RETENTION PERIOD     = INDEFINITE evidence / 30d rejected (2026-09-13)
