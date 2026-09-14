# Performance report — monitoring.v1 receiver

## The honest headline

**No performance measurement or load testing was carried out.** This report exists to say that clearly and to record what is therefore unknown, not to present numbers.

Every figure below is either a measured test-suite timing (which is not a performance measurement) or a structural observation about the code. None of it should be read as a capacity statement.

## 1. What was not measured

| Required measurement | Status |
|---|---|
| Ingestion throughput | **NOT MEASURED** |
| Validation latency | **NOT MEASURED** |
| Database write latency | **NOT MEASURED** |
| Projection latency | **NOT MEASURED** |
| API latency | **NOT MEASURED** |
| Frontend load time | **NOT MEASURED** |
| Memory | **NOT MEASURED** |
| CPU | **NOT MEASURED** |
| Storage growth | **NOT MEASURED** |
| Sustained rate / burst / duplicate burst / out-of-order burst / invalid burst / large valid payload | **NOT TESTED** |
| Slow clients, many viewers, large historical queries | **NOT TESTED** |

The repository already has a performance harness for the agent path (`ops/backend/scripts/measure_phase3_performance.py`, `tests/test_phase3_performance.py`). An equivalent for monitoring.v1 does not exist and would be the right next step.

## 2. Structural observations

These are code-reading observations, not measurements, and each is a hypothesis to be tested rather than a finding:

- **JSON Schema validation runs per message.** Validators are cached (`lru_cache` on `validator_for`), so schema parsing happens once per process, but `iter_errors` walks each envelope. This is the most likely hot spot and has never been timed.
- **Forward-compatibility stripping re-validates in a loop**, bounded at 8 passes. It only runs for newer-minor messages. A pathological document could cost 8 full validations.
- **Each message performs several small queries**: an evidence existence check, a sequence-state lookup, a projection lookup, plus inserts. A 1000-message batch is therefore several thousand round trips in one transaction. Batch-level prefetching was not implemented.
- **`projections.rebuild` loads and replays every evidence row** for an environment. Fine at thousands, unproven at millions, and it holds one session throughout.
- **`monitoring_raw_requests` stores whole request bodies** for quarantined traffic, with no retention policy. Storage growth under a persistently misbehaving publisher is unbounded — see `QUARANTINE_REPORT.md` §6.
- **The frontend re-evaluates freshness every second** for every visible row. That is cheap arithmetic over an already-fetched array, but it re-renders the list each tick; at a few hundred rows this has not been profiled.

## 3. Backpressure into LLS

The contract requires that the dashboard never propagate backpressure into LLS. Structurally it does not: the receiver is a plain request/response service with no callback, no blocking dependency on the publisher, and no reverse connection. A slow or failing receiver returns `503`, and the publisher's own durable queue absorbs the delay.

**This is a design property, not a measured one.** No test drives the receiver into saturation to confirm it degrades by returning 503 rather than by hanging.

## 4. Test-suite timings (not performance data)

For context only:

- ops backend monitoring suite: 60 tests, ~40 s wall clock, dominated by per-test SQLite setup and app construction
- full ops backend suite: ~13 minutes, dominated by pre-existing phase-3 simulation tests
- frontend monitoring tests: 32 tests, ~0.6 s of test execution

## 5. Status

| | |
|---|---|
| **NOT MEASURED** | every item in §1 |
| **UNKNOWN** | throughput, latency, memory, storage growth, degradation behaviour under load |
| **BLOCKED** | meaningful measurement needs a PostgreSQL instance and a synthetic monitoring.v1 generator; neither exists yet |

**No capacity or performance claim should be made about this receiver on the basis of this work.**
