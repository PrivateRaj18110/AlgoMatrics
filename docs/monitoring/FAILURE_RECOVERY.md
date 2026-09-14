# monitoring.v1 — failure and recovery validation

Companion to `STAGING_VALIDATION.md`. Every scenario below was executed against
the staging deployment: real PostgreSQL 17.6, real HTTPS, real process restarts.

## 1. The rule every scenario tests

**The receiver must never acknowledge a message it did not durably store.**

The producer deletes from its durable queue on a successful ACK, so a false ACK
does not degrade monitoring — it destroys the message. Every failure mode below
is judged first on that, and only then on how gracefully it failed.

## 2. Scenarios

Driver: `failure_recovery.py` (session scratchpad), which orchestrates the
database and receiver processes. The durable assertions have been folded into
`tests/test_monitoring_postgres.py` where they can be run without process
control.

| # | Scenario | Result |
|---|---|---|
| C1 | Normal operation before the outage | PASS |
| C1 | Database stopped, message submitted | PASS — refused, never acknowledged |
| C2 | Retry after the database returns | PASS — accepted |
| C2 | No duplicate evidence after recovery | PASS — 2 rows, sequence at 2 |
| C2 | Sequence state survived the outage | PASS — next sequence accepted |
| C3 | Outage *during* persistence | **PASS** — closed in phase two, see §7 |
| C4 | Slow database | PARTIAL — see §4 |
| C5 | Storage refuses writes | **PASS** — closed in phase two, see §8 |
| C5b | Literal disk exhaustion (ENOSPC) | **NOT TESTED** — see §8 |
| C6 | Restart while idle | PASS |
| C6 | Restart after an accepted message | PASS — evidence intact |
| C6 | Duplicates still recognised after restart | PASS |
| C6 | Sequence gap still refused after restart | PASS — 409 |
| C6 | Ordered recovery still works after restart | PASS |

Conservation after the full run: 5 evidence rows, 4 projections, 0 quarantined,
`accepted_count=5`, `duplicate_count=1`, `refused_gap_count=1`,
`last_accepted_sequence=5`. Every counter reconciles with what was submitted.

## 3. Finding: an outage produced a two-minute hang, not a refusal — FIXED

The first run passed C1 on the only criterion that matters — nothing was
acknowledged — but the *manner* of failure was wrong, and measurement showed why
that matters:

| | Before | After |
|---|---|---|
| Response to a message during an outage | client gave up after 122 s and 130 s | **HTTP 503 in ~12 s** |
| Status seen by the producer | ambiguous transport timeout, and in one case an unhandled 500 | the contract's retryable 503 |
| Worker occupancy per request | held for the full client timeout | bounded by the connect timeout |
| Recovery after the database returned | correct | correct, ~2 s |

Two causes, both fixed:

1. **No bound on waiting for the database.** The engine was created with
   SQLAlchemy's defaults, so an unreachable server was waited on indefinitely.
   Under a producer retrying on schedule, every worker would end up parked on a
   request that could never succeed — a database outage becoming total
   unavailability. `database_connect_timeout_seconds` (10),
   `database_pool_timeout_seconds` (10), `database_statement_timeout_ms`
   (30 000) and TCP keepalives now bound it. These are ceilings, not budgets:
   normal operation runs three orders of magnitude below them.

2. **`OperationalError` escaped as a 500.** A database that vanished mid-request
   surfaced as an unhandled error. It is now translated to `StorageUnavailable`,
   which the ingress already renders as 503. The distinction matters to the
   producer: 503 means *retry, your message is still good*.

Regression test: `test_an_unreachable_database_is_a_retryable_refusal_not_a_crash`,
which points the receiver at a closed port and asserts both the refusal type and
that it happens inside a bounded time. Deterministic, no process control needed.

## 4. Slow database — PARTIAL

What was measured: the receiver's behaviour under a *saturated* database, via
the load runs in `PERFORMANCE_BASELINE.md`. Latency degrades smoothly and
proportionally with concurrency, connections stay capped at the pool size (10),
and no request is acknowledged early. Resident memory is discussed in
`PERFORMANCE_BASELINE.md` — it rises slowly under sustained load rather than
staying flat, which is recorded there as unresolved.

What was **not** measured: artificially injected per-statement latency. Doing
that properly needs either a proxy that can delay packets or a database-side
fault injector, neither of which exists in this environment. The
`statement_timeout` ceiling is configured and its value is asserted, but a real
slow-query timeout has not been observed firing.

Recorded as PARTIAL rather than PASS.

## 5. What could not be tested here, and why

Two of the three items listed here in phase one were closed in phase two; the
history is kept because the reasoning for how they were closed matters.

**C3 — outage during persistence. CLOSED in phase two, see §7.** Phase one
concluded that reproducing a crash between the evidence write and the commit
needed a fault-injection hook in production code, and declined to add one. That
conclusion was wrong in an instructive way: the advisory lock added in the same
phase turned out to be a precise, externally controllable stall point, so the
window could be hit deterministically with no production change at all.

**C5 — storage failure. PARTIALLY CLOSED in phase two, see §8.** Filling the
volume that holds the staging cluster would risk the host's own storage and was
not attempted, so literal ENOSPC remains NOT TESTED. The condition it produces —
a durable write that fails — was reproduced two independent ways.

**C4 — injected per-statement latency. Still NOT TESTED**, see §4.

## 6. Restart semantics

All acceptance state lives in PostgreSQL, not in receiver memory, which is what
makes the restart results uninteresting in the best way: after a restart the
receiver recognised a duplicate of sequence 1, refused a gap at sequence 6, and
accepted sequence 5 — all reconstructed from the database with no warm-up step
and no in-memory cache to rebuild.


## 7. Outage during persistence — closed

The gate this document previously listed as NOT TESTED, saying a fault-injection
hook would be needed. It was not needed, because of something the earlier phase
had itself added.

The receiver takes a transaction-scoped advisory lock on
`(source_id, source_instance)` at the start of ingest. A control session holding
the same key parks the receiver **inside its own open transaction** — after it
has begun persisting, before it can commit. That is a precise and repeatable
stall point. The receiver's backend is then destroyed with
`pg_terminate_backend`.

The interruption is genuine: a live transaction killed mid-flight by the
database. The timing is deterministic rather than hoped for. And no test-only
branch exists in shipped code — it is an external session doing ordinary
PostgreSQL administration, which cannot be switched on by accident in
production.

| Check | Result |
|---|---|
| Receiver parked inside an open transaction | PASS |
| Backend terminated mid-persistence | PASS |
| Interrupted delivery **not** acknowledged | PASS — HTTP 503 |
| No evidence, no projection, no sequence state | PASS — all zero |
| Retry after interruption accepted | PASS |
| Accepted exactly once | PASS — 1 evidence row |
| Sequence continues correctly | PASS |
| Replay still recognised as a duplicate | PASS |
| Final state consistent | PASS — `last_accepted_sequence=2`, evidence=2 |

9 checks, 0 failures.

## 8. Storage refusing writes — closed, except literal ENOSPC

Filling the host volume is unsafe and was not attempted. **Literal ENOSPC
remains NOT TESTED** and is not claimed.

What ENOSPC produces at the application boundary — the durable write fails — was
reproduced two independent ways, because one mechanism could be handled by
accident:

| Mechanism | Result |
|---|---|
| `default_transaction_read_only = on` | HTTP 503 in 2.2 s, no evidence written |
| `REVOKE INSERT` on the evidence table | HTTP 503 in 2.0 s, no evidence written |
| Recovery after each | accepted, exactly once |
| Replay after recovery | duplicate, no second evidence row |

Both of these are real failures in their own right — a read-only replica, a
promoted standby, a revoked grant and a full volume all present identically to
the code under test.

### A defect this found

Both mechanisms originally surfaced as an unhandled **HTTP 500**.
`ReadOnlySqlTransaction` is an `InternalError` and permission denial is a
`ProgrammingError`; neither is an `OperationalError`, which was all the handler
caught.

No message was ever at risk — the contract routes any 5xx to bounded retry — but
500 tells the producer "something broke" where 503 tells it "storage did not take
this, try again", which is the honest answer and the one it is designed around.
Every database error that prevents the write now maps to 503.

## 9. What still cannot be tested here

| Item | Why |
|---|---|
| Literal disk exhaustion | Would risk the host's own storage |
| Injected per-statement latency | No fault injector available; §4 remains PARTIAL |
| Cross-host network partition | Single host |
