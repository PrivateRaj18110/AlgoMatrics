# monitoring.v1 — performance baseline

Companion to `PRODUCTION_CAPACITY_MODEL.md`.

**These are measurements of one staging configuration on one developer machine.**
They are not a production capacity statement. What they are for is comparing the
receiver's capability against the producer's contract-specified demand — and that
comparison is now decisive.

## 1. Methodology

| Item | Value |
|---|---|
| Receiver | uvicorn, 1 worker unless stated, TLS terminated in-process |
| Database role | `algomatric_receiver` — least privilege, cannot alter evidence |
| Database | PostgreSQL 17.6, same host, loopback, `scram-sha-256` |
| Host | Windows 11 Pro 10.0.26200, Python 3.14.4 |
| Container limits | none — not containerised |
| Transport | HTTPS over loopback, one keep-alive connection per publisher |
| Generator | `ops/backend/tools/monitoring_loadgen.py`, synthetic and marked as such |
| Warm-up | one request per connection, excluded from all samples |

Two points that materially change the numbers, both handled:

* **Connection reuse.** A fresh TLS handshake costs ~2.1 s here. Without
  keep-alive that lands inside the first sample and owns the p99. Every figure
  below uses one persistent connection per publisher, as a real producer does.
* **Distinct, ordered messages.** monitoring.v1 messages are content-addressed
  and must arrive in sequence, so replaying one fixture would measure the
  duplicate path. Every generated message is genuinely distinct and correctly
  ordered, so the receiver does the full validate-store-project work each time.

Test-suite wall clock is never used as a performance figure.

## 2. Concurrency matrix

150 messages per publisher, ~12 kB snapshot messages, **zero errors at every
level**.

| Concurrency | Messages | msg/s | p50 | p95 | p99 | max |
|---|---|---|---|---|---|---|
| 1 | 150 | 32.7 | 13.28 ms | 22.59 ms | 44.24 ms | 94.13 ms |
| 2 | 300 | 50.5 | 23.29 ms | 31.63 ms | 37.99 ms | 75.58 ms |
| 4 | 600 | 58.2 | 52.06 ms | 64.32 ms | 71.79 ms | 104.59 ms |
| 8 | 1,200 | 62.0 | 106.12 ms | 153.76 ms | 192.31 ms | 240.17 ms |
| 16 | 2,400 | **66.3** | 211.37 ms | 324.98 ms | 407.99 ms | 531.75 ms |
| 32 | 4,800 | 60.2 | 459.28 ms | 670.99 ms | 815.18 ms | 921.17 ms |

9,450 messages delivered across the matrix, no non-200 response at any point.

Two things the shape says:

* **Throughput peaks near 16 publishers (66 msg/s) and declines at 32.** Beyond
  the peak, added concurrency buys queueing, not work.
* **p50 grows almost exactly linearly with concurrency** — 459 ms at 32 is
  32 x 14 ms. That is the signature of requests being processed one at a time.

## 3. Request serialisation — measured, and deliberately not changed

The cause is visible in the code, not merely inferred from the curve. The
ingress is `async def` and then calls `receiver.ingest_message`, which is
synchronous and performs blocking database I/O:

    async def receive_message(...):
        raw_body = ...                       # async
        ack = receiver.ingest_message(...)   # synchronous, blocking

Blocking inside an `async def` endpoint blocks the event loop, so a second
request cannot begin until the first has finished its database work. Starlette
runs a plain `def` endpoint in a threadpool instead, which is the normal way to
host synchronous I/O.

### The decision

**Leave it unchanged.** This is a reversal of the previous phase's assessment,
and the evidence is the reason.

The previous phase listed serialisation as a production blocker while the
producer's publication rate was recorded as UNKNOWN. That rate is specified in
the canonical contract: **one delivery per service cycle, minimum cycle 10
seconds — a maximum of 0.1 msg/s, single-flight.**

| | msg/s |
|---|---|
| Receiver, 1 publisher, 1 worker | 32.7 |
| Receiver, peak (16 publishers) | 66.3 |
| **Producer maximum, per contract** | **0.1** |
| Headroom at the single-publisher figure | **~327x** |

The producer also never issues a second concurrent request: the contract states
it holds a per-instance delivery lock and sends one pending message per cycle.
So the receiver's concurrency behaviour is not on the path of any load the
contract permits.

Changing the endpoint to `def` is a one-word change with whole-request-path
consequences — threadpool sizing, interaction with the per-instance advisory
lock, and the failure semantics validated in `FAILURE_RECOVERY.md`. Making that
change to gain throughput that is already 300x surplus would be spending
correctness risk on nothing.

**Recorded as a known characteristic, not a blocker.** It becomes worth revising
only if the producer's delivery model changes, or if many LLS services publish
to one receiver — both of which would be signalled by the contract or by an
owner decision, not by this measurement.

## 4. Sustained load — 15 minutes

Run at concurrency 4 against a **two-worker** receiver (see §6 and the note
below), far above the producer's contract ceiling of 0.1 msg/s. The point is to
compress a long period of normal operation into a short one and look for drift.

| Metric | First sample | Last sample |
|---|---|---|
| Throughput | 65.2 msg/s | 82.4 msg/s (mean 59.3) |
| p50 latency | 36.6 ms | 26.3 ms |
| Resident memory (all worker processes) | 220.3 MB | 233.3 MB |
| Database connections | 5 | 9 (pool size 10, overflow unused) |
| Dead tuples | 303 | 794, cycling — autovacuum keeping up |

    duration          905 s over 72 rounds
    messages accepted 28,600
    evidence table    157.5 MB for 28,600 rows  (5,508 bytes/row)
    database size     14.6 MB -> 292.1 MB

**Throughput and latency improved over the run** rather than degrading — the
opposite of what a leak or bloat problem looks like. Connections stayed inside
the pool. Autovacuum kept dead tuples cycling rather than accumulating.

### Memory: rising, unresolved *(at the time — see §7 for the resolution)*

Resident memory rose from 220.3 MB to 233.3 MB across 28,600 messages — roughly
**0.45 KB per message**, and it did not flatten within the run.

This was **not** claimed to be a leak, and not claimed to be benign. Fifteen
minutes cannot distinguish a genuine leak from a working set growing to its
steady state, and the honest position was that it was uncharacterised.

Recorded as PARTIAL under resource bounds. A multi-hour run is what resolves it,
and §7 is that run: over 4.17 hours and 746,400 messages the curve reaches a
plateau within roughly the first 35,000 messages and then stops rising. **The
15-minute window had measured the initial rise and nothing else.**

### 200 messages not delivered — a defect in the test tool, not the receiver

The run attempted 28,800 messages and stored 28,600. The 200 missing were
investigated rather than rounded away:

* The receiver's access log shows **no** non-200 response during the run. Every
  422 in that log (125) is accounted for by an earlier, already-fixed generator
  bug that predates the run.
* So those requests never reached the application — they failed at the transport
  layer, and the generator held one keep-alive connection per publisher with no
  reconnect. A single dropped socket therefore lost that publisher's entire
  remaining round, which matches the lumpy count.
* Re-running the identical loop three times afterwards: **1,200/1,200, zero
  errors, zero quarantine.**

The generator now reconnects once per message. Recorded because a measurement
that looks like receiver errors and is really a broken test client is worth
reporting as such, not quietly re-run until clean.

### A note on the configuration this actually ran on

This run and the per-type storage measurements were taken against a **two-worker**
receiver, not the single worker the concurrency matrix used. That was not
intended: the receiver stop script killed the launcher process rather than the
detached uvicorn supervisor that owned the port, so an earlier "restart with one
worker" silently left the two-worker deployment serving. The script now stops
whatever owns the port.

Storage figures are worker-independent and stand. The sustained figures are
labelled two-worker here rather than silently attributed to the matrix
configuration.

## 5. Storage per message type

> Small-sample figures (n=120 per type). **§8 supersedes these** with a
> 750,400-message measurement; the per-type *ratios* below still hold, the
> absolute bytes/row do not.

**MEASURED**, 120 messages of each type, bytes/row includes indexes:

| Message type | Wire size | Stored per evidence row | Ratio |
|---|---|---|---|
| `monitoring.events` | 98,314 B | 8,055 B | **12.2 : 1 compression** |
| `monitoring.snapshot` | 11,953 B | 6,690 B | 1.8 : 1 |
| `monitoring.incidents` | 1,963 B | 3,959 B | expands — fixed overhead dominates |
| `monitoring.forensic_reference` | 1,224 B | 3,891 B | expands — fixed overhead dominates |

The most useful finding here corrects an assumption in the capacity model: an
80x spread in *wire* size becomes roughly a **2x** spread in *stored* size.
PostgreSQL TOAST compresses the large JSON message types heavily, while small
messages are dominated by fixed row and index overhead — so a production mix
weighted toward `monitoring.events` costs far less storage than its wire size
suggests.

At n=120 the per-row figures include a fixed page and index cost that amortises
away at scale; treat them as upper bounds. The 3,200-message snapshot run in the
previous phase measured 5,583 bytes/row, which is the better large-n figure.

## 6. Multi-worker

Two workers were tested for **safety**, not throughput (see
`STAGING_VALIDATION.md`). The advisory lock holds across operating-system
processes: 20 concurrent identical deliveries across two workers yielded exactly
one acceptance and one evidence row, ordered acceptance behaved correctly, and
two different bodies for one sequence produced exactly one acceptance.

Safe, but **not enabled**: at 0.1 msg/s of contract-permitted demand there is no
throughput reason to run more than one worker, and §23 is explicit that worker
count must not be raised for throughput alone.

## 7. Memory characterisation — 4.17 hours, 746,400 messages

The measurement the previous phase asked for, run against a **single worker**
(the configuration the container actually uses) on a quiet machine.

### Why it is phased rather than simply longer

A longer run of the same shape would not have settled anything. RSS rising while
messages are accepted is equally consistent with per-message retention (a real
leak) and per-time growth (a background task, a cache, allocator behaviour that
would happen with no traffic at all). At a constant rate, messages and seconds
advance together, so the two are indistinguishable.

So the run is phased, and the phases differ deliberately:

| Phase | Duration | Traffic | `capture_ref` | Purpose |
|---|---|---|---|---|
| LOAD-A | 5,996 s | 366,400 messages | **per message** | projections grow 1:1 — pessimistic |
| IDLE | 2,909 s | **none** | — | separates time-driven from message-driven |
| LOAD-C | 5,997 s | 379,200 messages | **stable** | projections bounded — realistic |
| restart | — | 4,000 messages | stable | does a restart return to baseline? |

### Run integrity

| | |
|---|---|
| Rounds × 400 messages | 1,866 × 400 = **746,400** |
| Evidence rows at end | **746,400** |
| Quarantine rows | **0** |
| Raw request rows (refusals) | **0** |
| Audit rows | 746,400 (one per accepted message) |
| `sequence_state` rows | 3,734 = 1,866 rounds × 2 publishers + 2 |
| Generator failures | 0 |

Every message sent was accepted. No rejections, no duplicates, no errors, and
the row counts reconcile exactly rather than approximately.

### Result

    phase    duration   messages    RSS first -> last    min      max     slope vs messages
    LOAD-A    5,996s     366,400    107.39 -> 123.72   107.39   127.54    +0.0074 KB/msg (r2 0.08)
    IDLE      2,909s           0    123.72 ->  27.16    27.16   123.72    n/a
    LOAD-C    5,997s     379,200     52.24 -> 118.06    52.24   122.09    +0.0443 KB/msg (r2 0.14)

**The slopes are not the finding. Their r² is.** At r² = 0.08 and 0.14, a
straight line explains almost none of the variation — which is the signature of
a curve that is not a line. Fitting one and quoting the gradient is exactly the
error the 15-minute run made.

The trajectory says it plainly. RSS by equal tenths of each load phase:

| Slice | LOAD-A mean RSS | LOAD-C mean RSS |
|---|---|---|
| 1 | 118.48 | 87.76 |
| 2 | 123.45 | 117.73 |
| 3 | 123.01 | 118.58 |
| 4 | 123.42 | 118.13 |
| 5 | 123.41 | 117.69 |
| 6 | 123.70 | 117.73 |
| 7 | 123.51 | 117.86 |
| 8 | 123.75 | 118.05 |
| 9 | 123.19 | 116.92 |
| 10 | 123.34 | 117.76 |

**Both phases rise during their first tenth and are flat for the remaining
nine.** LOAD-A holds 123.0–123.8 MB across its last 330,000 messages; LOAD-C
holds 116.9–118.6 MB across its last 340,000.

Restricting the fit to the final 2,000 seconds of each phase — after the rise —
the slope is **negative** in both:

| Phase | Final-2000s slope | Projected over 1,000,000 further messages |
|---|---|---|
| LOAD-A | −0.0093 KB/msg | **−9.1 MB** |
| LOAD-C | −0.0031 KB/msg | **−3.1 MB** |

### The IDLE phase, and an important caveat about RSS

RSS held at **exactly 123.71 MB** for the first eight tenths of the idle phase —
no traffic, no drift, not one megabyte. Then, roughly 2,000 seconds in, it fell
to **27.16 MB**.

That drop is the operating system trimming the working set of an idle process,
not the application releasing anything: LOAD-C then re-faults those pages back
in, which is the whole of its first-tenth "rise" from 52.24 MB. It is also why
LOAD-C's headline slope is *larger* than LOAD-A's despite having bounded
projections — the number is measuring page re-entry, not allocation.

**Caveat, stated rather than buried: this is Windows working-set size.** It is a
faithful measure of resident pages, but the OS is an active participant in it.
Linux under a container memory limit is a different accounting regime, and it is
`NOT TESTED` here.

### Restart

| | RSS |
|---|---|
| Cold start, empty database | 106.10 MB |
| End of LOAD-C, 746,400 messages stored | 118.06 MB |
| **After restart, idle, 746,400 rows still in the database** | **102.75 MB** |
| After restart + 4,000 messages | 107.99 MB |

A restart returns resident memory to baseline, and the baseline does **not**
depend on how much evidence is already stored — the receiver holds no evidence
in memory. The restarted process then begins the same rise toward the same
plateau.

### Classification

    RESOLVED — the resident set reaches a plateau and stops rising

Specifically:

* **Not message-driven beyond the initial rise.** Flat across 330,000 and
  340,000 consecutive messages respectively; negative slope at steady state.
* **Not time-driven.** Held to 0.01 MB over 2,000 seconds of complete idleness.
* **Not cumulative across restarts.** Baseline is independent of stored volume.
* **The earlier 0.45 KB/message was the initial rise, measured in a window too
  short to contain anything else.** That figure is superseded, not contradicted:
  it correctly described the first fifteen minutes.

What is **not** claimed: that there is no leak of any kind under any workload.
This run used one message type at high rate on Windows. A leak smaller than the
±3 MB oscillation of the plateau would not be visible, and Linux/container
behaviour is `NOT TESTED`.

### Peak resident memory, single worker

    MEASURED   peak RSS over the whole run          127.54 MB
    MEASURED   steady-state plateau                 117 - 124 MB
    MEASURED   cold start                           102.75 - 106.10 MB

This is the figure that belongs in the deployment manifest. The 220–233 MB
previously quoted there was a **two-worker** measurement, and the container runs
one worker.

### Throughput, and what it costs to grow a projection table

| Phase | `capture_ref` | Projection rows added | Mean throughput | Mean p50 |
|---|---|---|---|---|
| LOAD-A | per message | **+366,400** for 366,400 messages | 80.4 msg/s | 23.5 ms |
| LOAD-C | stable | **0** for 379,200 messages | 86.3 msg/s | 21.8 ms |

One projection row served all 379,200 LOAD-C messages. The receiver's projection
behaviour is bounded by distinct keys exactly as designed; the 1:1 growth in
earlier runs came from the load generator assigning a unique `capture_ref` to
every message. See §8 for what that costs in storage, and
`PRODUCTION_CAPACITY_MODEL.md` for why which of the two applies in production is
`UNKNOWN`.

Both figures are far above the contract's 0.1 msg/s ceiling. Throughput is not
the constraint; §8 is.

## 8. Storage per message — the large-n measurement

**MEASURED** over 750,400 stored messages on PostgreSQL 17.6. This supersedes
the n=3,200 and n=120 figures in §5: the fixed page and index costs that
dominate small samples have amortised away.

| Table | Heap | Indexes | Total (incl. TOAST) | Rows | Bytes/message |
|---|---|---|---|---|---|
| `monitoring_evidence` | 768.5 MB | 254.3 MB | 4,131.2 MB | 749,830 | **5,505** |
| `monitoring_audit` | 161.8 MB | 40.0 MB | 201.9 MB | 750,090 | **269** |
| `monitoring_projections` | 329.6 MB | 74.4 MB | 1,513.7 MB | 366,697 | **4,128 per projection row** |
| `monitoring_sequence_state` | 1.1 MB | 15.6 MB | 16.8 MB | 3,734 | bounded by instance count |
| `monitoring_quarantine` | 0 | 0 | 0 | 0 | — |
| `monitoring_raw_requests` | 0 | 0 | 0 | 0 | — |

Measured directly as phase deltas, which is the cleaner reading because each
phase used exactly one projection scenario:

| | Evidence growth | Whole-database growth | Non-evidence remainder |
|---|---|---|---|
| LOAD-A (`capture_ref` per message) | 5,544 B/msg | **9,962 B/msg** | 4,418 B/msg |
| LOAD-C (`capture_ref` stable) | 5,468 B/msg | **5,759 B/msg** | 291 B/msg |

**A changing `capture_ref` costs 1.73× the storage per message of a stable one.**
The evidence cost is identical either way — the difference is entirely the
projection table and its unique index.

### What these figures do and do not include

| Component | Status |
|---|---|
| Evidence, audit, projections, sequence state, their indexes, TOAST | **MEASURED** |
| WAL | **MEASURED as a steady-state floor**: 23 segments, 368 MB. WAL is recycled, so this is a fixed overhead, not per-message growth. Archiving would change that. |
| Backups | **NOT MEASURED** — no backup was configured |
| WAL archiving / PITR | **NOT MEASURED** |
| Replication | **NOT MEASURED** |
| Autovacuum headroom / bloat at steady state | **NOT MEASURED** over a long horizon |

So the per-message figures above are a **database** growth model, not a full
disk-capacity model. A production volume must also carry WAL (a floor, measured
at 368 MB here), plus whatever backup and archiving policy is chosen — which is
`UNKNOWN` until the retention decision is made.

## 9. What was not measured

* Production-class hardware, and any non-loopback network.
* A remote database — everything here is same-host loopback.
* Concurrent dashboard readers alongside ingest.
* Container or orchestrator resource limits, and Linux memory accounting. The
  memory characterisation is Windows working-set on the host.
* Backups, WAL archiving, PITR and replication overhead.
* Production message mix. Every load figure here uses one message type at a
  time; the production mix is UNKNOWN.

None of these is claimed.
