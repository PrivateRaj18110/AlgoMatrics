# monitoring.v1 on PostgreSQL — compatibility audit and validation

Companion to `STAGING_VALIDATION.md`. Everything here was measured against a
real PostgreSQL 17.6 database, not inferred from the SQLite suite.

## 1. Why this document exists

The previous phase validated the receiver on SQLite. SQLite differs from
PostgreSQL in ways that matter to this receiver specifically:

| Behaviour | SQLite | PostgreSQL |
|---|---|---|
| Concurrent writers | serialised by the database | genuinely concurrent under MVCC |
| Read-then-write races | cannot occur between writers | occur under READ COMMITTED |
| Constraint violation | fails the statement | **aborts the whole transaction** |
| Type checking | permissive affinity | strict; no boolean/integer coercion |
| `DateTime(timezone=True)` | returns naive datetimes | returns aware datetimes |
| Advisory locks | none | available, transaction-scoped |

Each row of that table produced at least one finding below.

## 2. Environment

| Item | Value |
|---|---|
| PostgreSQL | 17.6 on x86_64-windows, official EnterpriseDB binary distribution |
| Cluster | private, loopback-only, port 55432, `scram-sha-256` |
| Database | `algomatric_monitoring_staging` |
| Role | `algomatric_staging` — owner of the database, **not** a superuser |
| Driver | `psycopg` 3.3.4 via `postgresql+psycopg://` |
| Application | `ops/backend`, branch `feat/monitoring-v1-receiver` from `359d87e` |

Credentials are generated per session into the session scratchpad. They appear
in no source file, no fixture, no document and no log.

## 3. Findings

### 3.1 The migration chain could not be applied to PostgreSQL at all — FIXED

`alembic upgrade head` failed on revision `a3c7e1d94b62`:

```
sqlalchemy.exc.ProgrammingError: (psycopg.errors.DatatypeMismatch)
column "acknowledged" is of type boolean but default expression is of type integer
HINT:  You will need to rewrite or cast the expression.
```

Two columns declared `sa.Boolean()` with `server_default=sa.text("0")`. SQLite
accepts the integer `0` as a boolean default; PostgreSQL refuses it. The
migration had therefore only ever run on SQLite, and **no PostgreSQL deployment
of this schema had ever been possible.**

Fixed by replacing both with `sa.false()`, which renders `false` on PostgreSQL
and `0` on SQLite. Editing a historical revision is normally wrong; it is
correct here because the revision has never been applied to any PostgreSQL
database — it *cannot* be — and both affected tables are dropped by the next
revision. A follow-up migration could not have helped, because the chain could
not reach one.

Scope of the search: every migration was checked for the same class of defect.
`sa.Boolean` appears three times in total; the third (`e1fd66220c23`) has no
server default. No other PostgreSQL-hostile construct was found —
`batch_alter_table` is a no-op outside SQLite, and every column type in use
(`String`, `Text`, `Integer`, `BigInteger`, `Float`, `DateTime(timezone=True)`,
`LargeBinary`) is portable.

**Status: PASS after fix.** Full chain applies; `downgrade -1` then `upgrade
head` round-trips correctly.

### 3.2 Ordered acceptance had a read-then-write race — FIXED

Reproduced against PostgreSQL with two concurrent deliveries of *different*
messages for the same new `(source_id, source_instance)`:

```
IntegrityError: duplicate key value violates unique constraint
"uq_mon_sequence_instance"
DETAIL:  Key (source_id, source_instance)=(lls-contract-fixture, order-a-01)
         already exists.
```

The ingest path reads the instance's last accepted sequence, decides, and then
writes the new one. Under READ COMMITTED two deliveries for one instance can
both read the same value before either writes. Two outcomes follow, both wrong:

* both decide "accept" for the same sequence, and
* both attempt to create the instance's first state row, so the loser surfaces a
  raw `IntegrityError` — an HTTP 500 rather than any defined contract outcome.

SQLite cannot exhibit this: it serialises writers, so the second delivery always
finds the first already committed. The identical-message case *did* pass even on
PostgreSQL, because identical bodies share a content address and collide on the
evidence primary key, which was already handled. Only *different* messages for
one instance reach the unhandled path.

Fixed with a transaction-scoped advisory lock on `(source_id, source_instance)`,
taken before the duplicate check. Verified directly:

| Condition | Result |
|---|---|
| Advisory lock actually taken on PostgreSQL | `ExclusiveLock`, granted |
| Second writer, same instance | blocked until commit |
| Second writer, different instance | acquired in 0.00s |

It constrains nothing the contract did not already constrain — monitoring.v1
requires an instance's messages to be accepted in order — and different
instances and sources stay fully parallel. It is a no-op on SQLite.

**Status: PASS after fix.**

### 3.3 Evidence was immutable only at the ORM object layer — FIXED

`MonitoringEvidence` carries `before_update` / `before_delete` mapper events.
Measured against PostgreSQL with the application's own role and session:

| Path | Before | After |
|---|---|---|
| `session.flush()` after attribute change | REFUSED (`EvidenceIsImmutable`) | REFUSED |
| `session.delete(row)` | REFUSED (`EvidenceIsImmutable`) | REFUSED |
| `session.execute(update(...))` | **ALLOWED — 1 row rewritten** | REFUSED |
| `session.execute(delete(...))` | **ALLOWED — 1 row destroyed** | REFUSED |
| Raw SQL `UPDATE` / `DELETE` | **ALLOWED** | REFUSED |
| `INSERT` (new evidence) | allowed | allowed |

SQLAlchemy Core bulk statements emit no mapper events. The deployment
architecture permits direct database writes — the application role owns the
table — so the ORM guard was not the guarantee the rest of the system relies on.

Fixed in migration `c7f41a92d8e5` with a row-level trigger that raises on UPDATE
and DELETE. It is purely additive: no table dropped, no row touched, no column
changed. `TRUNCATE` remains permitted — row triggers do not fire for it, it needs
table-owner privilege, and it cannot target a single row, so it stays usable for
resetting a test database while being useless for quietly editing history.

Deletion is blocked outright rather than given an escape hatch, so a future
approved retention job must drop the trigger in its own reviewed migration.
See `RETENTION_POLICY.md`.

**On SQLite the ORM guard remains the entire guarantee.** That is stated here
rather than assumed, because the offline suite runs on SQLite.

**Status: PASS after fix.**

### 3.4 Pre-existing schema drift, unrelated to monitoring — NOT FIXED, out of scope

`alembic check` reports three indexes present in the migrations but absent from
the ORM models:

```
ix_eod_datasets_raw_deleted_at   (eod_datasets)
ix_machines_last_recovery_at     (machines)
ix_machines_recovery_state       (machines)
```

Classified **PRE-EXISTING**. Evidence: all three are created by migrations
`f4a9c3d2b8e1` and `ad9f3b6c2e41`, both from commit `1bf5726` ("complete pre-live
telemetry platform"), which predates the monitoring.v1 work in `359d87e`; the
corresponding model columns never declared `index=True`; and the tables are
`eod_datasets` and `machines`, which this phase does not touch.

**No monitoring table shows any drift.** Left alone deliberately: fixing
unrelated tables in a monitoring phase would widen the change surface for no
gain here.

### 3.5 Two dead configuration settings — NOT FIXED, recorded

`monitoring_max_body_bytes` (8 MiB), `monitoring_max_envelope_bytes` (256 KiB)
and `monitoring_max_batch_items` (1000) are defined in `app/core/config.py` and
referenced nowhere. They are leftovers from the superseded `monitoring-export/v1`
proposal, which had a batch wrapper; monitoring.v1 does not.

They are harmless but misleading: an operator tuning `MONITORING_MAX_BODY_BYTES`
would change nothing, and might reasonably believe they had raised a limit. The
real limit is `contract.LIMITS.request_bytes` (1 MiB), which comes from the
producer's contract and is not operator-tunable by design.

Recorded rather than removed — deleting settings is a compatibility decision for
whoever owns the deployment configuration.

## 4. Validation results

All against the real database. Test module: `tests/test_monitoring_postgres.py`,
31 tests, skipped in full unless `MONITORING_PG_URL` is set.

### 4.1 Schema

| Check | Result |
|---|---|
| Migration `upgrade head` | PASS |
| Deployed column types (`varchar`, `bigint`, `timestamptz`, `text`) | PASS |
| Evidence primary key is the content address | PASS |
| `alembic check` — monitoring tables | PASS, no drift |
| `downgrade -1` restores the superseded shape | PASS |
| `upgrade head` again | PASS |

### 4.2 Evidence persistence

Every field of an accepted message verified against the fixture it came from:
identity and recomputed content address, request digest, `source_id`,
`source_instance`, `source_sequence` (as the producer's **string**, with the
parsed ordinal beside it), `message_type`, `schema_version`, both environments
separately, `generated_at` / `received_at`, `source_as_of`, `coverage`,
`freshness`, `trust`, `runtime` as an array, `capture_ref`, and the whole message
recoverable byte-for-byte as canonical JSON.

`timestamptz` round-trips timezone-aware, and `generated_at` equals the
producer's value exactly. PASS.

### 4.3 Duplicates and concurrency

| Test | Result |
|---|---|
| Identical redelivery x4 | one evidence row, one projection, stable ACK identity |
| Redelivery after later sequences | still `duplicate`, sequence state unmoved |
| Concurrent identical delivery, 2 workers | exactly 1 accepted, 1 duplicate |
| Concurrent identical delivery, 5 workers | exactly 1 accepted, 4 duplicates |
| Concurrent identical delivery, 10 workers | exactly 1 accepted, 9 duplicates |
| Concurrent identical delivery, 20 workers | exactly 1 accepted, 19 duplicates |
| Concurrent *different* messages, same sequence | exactly 1 accepted (was: unhandled `IntegrityError`) |
| Concurrent first messages, 8 workers | one sequence-state row, no error escapes |

No unhandled `IntegrityError`, no duplicate evidence, no duplicate projection, no
inconsistent ACK identity at any concurrency level tested.

### 4.4 Sequence semantics

`1, 2, 3` accepted; `5` refused with 409 and last-accepted retained at 3; `4`
accepted; `5` then accepted. A refused sequence produces **no evidence row and
no projection**, and is **not** quarantined — it is a well-formed message
arriving early, not a defective one. A new `source_instance` starts its own
sequence at 1. PASS.

### 4.5 Quarantine

Unsupported schema version, forged `message_id`, duplicate JSON keys, excessive
nesting and an oversized string each quarantine with the expected reason,
produce zero evidence and zero projections, and preserve the original request
bytes. Quarantine survives its own transaction — relevant on PostgreSQL, where a
statement error aborts the transaction and a careless refusal path could lose
the record of its own refusal. PASS.

### 4.6 Projections

Knowledge states preserved exactly: `STALE` stays `STALE`, `INCOMPLETE` stays
`INCOMPLETE`, `UNTRUSTED` stays `UNTRUSTED`, `SYNTHETIC_CLOCK` preserved,
explicit `null` stays `null`, `runtime` stays an array, and `source_environment`
remains the producer's market reality rather than our deployment tier.

Message types are separated, not merged: `order_b` sequences 1-3 are a snapshot,
an events message and an incidents message, and produce three projections. A
later message of the *same* type supersedes the earlier one; a redelivery of the
superseded message does not drag the projection backwards; and superseding never
removes the evidence it moved on from. PASS.

### 4.7 Projection rebuild

Rebuilt from evidence twice over an eight-message corpus. First rebuild equals
the incrementally maintained state across all 17 projected columns; second
rebuild is identical to the first; evidence is unchanged hash-for-hash
(`md5(message_json)` and `request_sha256` per row). PASS.

### 4.8 Conservation

Over a mixed run of accepted, duplicate, sequence-refused and quarantined
traffic: accepted messages and only those became evidence; refused and
quarantined material produced no evidence; projections matched the distinct
message types accepted; and the sequence-state counters
(`accepted_count`, `duplicate_count`, `refused_gap_count`) reconciled exactly.
PASS.

## 4.9 Persistence interrupted mid-transaction — closed

The previous phase left this NOT TESTED, saying a fault-injection hook would be
needed. It turned out not to be, because of something that phase itself added.

The receiver takes a transaction-scoped advisory lock on
`(source_id, source_instance)` at the start of ingest. A control session holding
the same key parks the receiver **inside its own open transaction**, after it has
begun persisting and before it can commit — a precise, repeatable stall point.
The receiver's backend is then destroyed with `pg_terminate_backend`.

The interruption is real (a live transaction killed mid-flight) and the timing is
deterministic. No test-only branch exists in shipped code, and nothing here can
be switched on accidentally in production: it is an external session doing
ordinary PostgreSQL administration.

| Check | Result |
|---|---|
| Receiver parked inside an open transaction | PASS — backend identified and confirmed blocked |
| Backend terminated mid-persistence | PASS |
| Interrupted delivery **not** acknowledged | PASS — HTTP 503 |
| No evidence, no projection, no sequence state | PASS — all zero |
| Retry after interruption accepted | PASS |
| Accepted exactly once | PASS — 1 evidence row |
| Sequence continues correctly | PASS |
| Replay still recognised as duplicate | PASS |
| Final state consistent | PASS — last_accepted_sequence=2, evidence=2 |

## 4.10 Storage refusing writes — closed, except literal ENOSPC

Filling the host volume is unsafe and was not attempted; literal ENOSPC remains
NOT TESTED. What ENOSPC *produces* at the application boundary — the durable
write fails — was reproduced two independent ways:

| Mechanism | Result |
|---|---|
| `default_transaction_read_only = on` | HTTP 503, no evidence written, clean recovery |
| `REVOKE INSERT` on the evidence table | HTTP 503, no evidence written, clean recovery |
| Replay after recovery | duplicate, no second evidence row |

Both previously surfaced as an unhandled **500**, because `ReadOnlySqlTransaction`
is an `InternalError` and permission denial a `ProgrammingError` — neither is an
`OperationalError`. The handler now maps any `DBAPIError` that prevented the
write to the contract's retryable 503. See `TLS_VALIDATION.md` §5.

## 4.11 Timestamps are canonical under any session timezone

§18 asks for at least two PostgreSQL timezone settings. Five were used, chosen to
be awkward — two half-hour offsets and one at +12:45:

| Session timezone | Driver returned | API rendered |
|---|---|---|
| UTC | `...T09:01:34.627414+00:00` | `...T09:01:34.627414Z` |
| Asia/Kolkata | `...T14:31:34.627414+05:30` | `...T09:01:34.627414Z` |
| America/New_York | `...T05:01:34.627414-04:00` | `...T09:01:34.627414Z` |
| Australia/Adelaide | `...T18:31:34.627414+09:30` | `...T09:01:34.627414Z` |
| Pacific/Chatham | `...T21:46:34.627414+12:45` | `...T09:01:34.627414Z` |

One distinct rendered value across all five, with a `Z` suffix, no numeric
offset, and still the producer's exact instant. PASS.

## 4.12 Two workers are safe

The advisory lock is a PostgreSQL *advisory* lock, so it must hold across
operating-system processes, not merely across threads. Tested against a receiver
running two workers:

| Check | Result |
|---|---|
| 2 / 10 / 20 concurrent identical deliveries | exactly 1 accepted each time, 1 evidence row, 0 errors |
| ACK identity across workers | one `message_id` and one `sha256` per group |
| Ordered acceptance 1,2,3 → 5 (409) → 4 → 5 | correct |
| Sequence state after the run | `last_accepted_sequence=5`, evidence=5 |
| Same sequence, two different bodies, delivered together | exactly 1 accepted, the other 409 |

14 checks, 0 failures. **Safe, but not enabled** — see `PERFORMANCE_BASELINE.md`
§6 for why more than one worker is unnecessary.

## 4.13 The evidence table was truncatable by the application — closed

Covered in full in `DEPLOYMENT_VALIDATION.md` §1. In short: the append-only
trigger does not fire for `TRUNCATE`, and the application owned the table, so its
own credential could empty the forensic record in one statement. Closed by role
separation, verified, and the producer harness still passes 11/11 with the
receiver running under the restricted role.

## 5. What is not covered here

* Container and orchestration behaviour — this cluster is not containerised.
* Replication, failover and managed-database semantics — single instance.
* Production-like hardware. See `PERFORMANCE_BASELINE.md` for what the numbers
  do and do not support.
* Immutability below the ORM **on SQLite** — the trigger is PostgreSQL-only.
