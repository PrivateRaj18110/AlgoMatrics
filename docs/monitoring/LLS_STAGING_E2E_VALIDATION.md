# LLS ↔ Algomatric staging end-to-end validation

**Date:** 2026-09-11
**Outcome:** validation stopped at step 2 (contract comparison). The remaining steps are downstream of a contract match and were not run.

Full field-by-field analysis: [LLS_CONTRACT_COMPATIBILITY_REPORT.md](LLS_CONTRACT_COMPATIBILITY_REPORT.md).

---

## 1. Contract compatibility — **FAIL**

`schemas/monitoring-export/v1/` and the LLS `monitoring.v1` schema are two
independently designed contracts, not two versions of one.

```
LLS fixtures marked producer_valid : 19
Accepted by the Algomatric schema  :  0 / 19
```

Of the six envelope fields that share a name, only three (`source_id`,
`source_instance`, `generated_at`) match in type and meaning. Eleven further
fields differ in name, type, location or semantics, and each contract carries
concepts the other lacks entirely — `message_type`, `observer`, `evidence`,
`salvage` on the LLS side; `entity`, `revision`, `stale_after` on ours.

Neither side was changed. Neither schema was edited.

## 2. Fixture compatibility — **FAIL**

| Probe | Result |
|---|---|
| `POST /api/monitoring/v1/messages` (path LLS expects) | **404**, route does not exist |
| LLS message body → `/api/v1/monitoring/export` | **400**, `'messages' is a required property` |
| `receiver_acceptance_test.py` against our endpoint | **refused to start** — the harness enforces its own path |

The LLS acceptance harness cannot be aimed at the receiver without editing the
harness. It is the authoritative artifact, so it was left untouched.

Package integrity itself is **PASS**: `--dry-run` reports
`{"status":"dry-run-ok","messages":22,"cases":11}`, and the runner imports only
the standard library — no LLS code, database or filesystem dependency. Vendored
verbatim to [`tests/fixtures/lls-monitoring-v1-handoff/`](../../tests/fixtures/lls-monitoring-v1-handoff).

## 3. Canonical JSON — **PASS (algorithm), FAIL (scope)**

The mandatory gate, and the one clearly positive result.

| Check | Result |
|---|---|
| LLS fixture bytes are `sort_keys=True, separators=(",",":"), ensure_ascii=False` | **yes** |
| Re-canonicalising with the Algomatric `contract.canonical_json` | **byte-identical** |
| `sha256(raw bytes)` vs manifest `sha256` | **match** (`de7846f8…288e`) |

**The serialisation algorithm is identical on both sides**, verified against a
real producer fixture. The risk flagged as the top interoperability hazard in
the previous report does not exist.

The hash *scope* differs — LLS hashes the whole request body, we hash the
`observation` sub-object — which is the cheapest mismatch in the whole comparison
to resolve, and Algomatric owns it.

The receiver was **not** patched to make any of this pass.

## 4. PostgreSQL — **BLOCKED — NOT RUN**

No PostgreSQL is available in this environment: no `docker`, no `psql`, no local
install. Every result the receiver has ever produced is against **SQLite**, and
none of it is reported here as a PostgreSQL result.

Untested, in full: migration on PostgreSQL, insert, duplicate, conflict,
sequence gap, quarantine, projection, projection rebuild, restart, rollback,
concurrent delivery.

## 5. Steps not run — and why

| Step | Status |
|---|---|
| 3. Fixture acceptance suite | **NOT RUN** — every message fails schema validation; the run would measure the mismatch, not the receiver |
| 4. Identity semantics against LLS fixtures | **NOT RUN** — blocked by §1 |
| 5. Pipeline verification with real messages | **NOT RUN** — blocked by §1 (the pipeline order itself is verified by the existing suite, see `MONITORING_V1_RECEIVER_REPORT.md`) |
| 6. PostgreSQL staging | **BLOCKED** — no instance available (§4) |
| 7. Failure/recovery, HTTP status matrix, TLS | **NOT RUN** — the 4xx/5xx contract cannot be exercised until a request can be accepted at all |
| 9. Environment isolation with staging evidence | **NOT RUN** — LLS `environment` values (`offline_fixture`, `live_trading`, …) are a different axis from ours (`production`, `staging`, …); the boundary cannot be tested until that is resolved |
| 10. UI verification with real received evidence | **NOT RUN** — no LLS evidence can be stored, so there is nothing real to render |
| 11. Security | **PARTIAL** — credential scoping, foreign-source rejection and admin/publisher separation are covered by the existing suite against synthetic messages. TLS verification, certificate rejection and redirect-downgrade were **NOT TESTED**; staging ran over plain HTTP on loopback |
| 12. Performance | **UNKNOWN — NOT MEASURED**, every metric: ingestion latency, DB write latency, projection latency, throughput, queue/retry, memory, CPU, database growth |

## 6. What this exercise did establish

Not everything here is negative, and two results are worth keeping:

1. **Canonical JSON is settled** (§3) — the single highest-risk unknown from the
   previous report is now a verified match against a real producer artifact.
2. **The two designs agree on semantics far more than on syntax.** Both use
   explicit knowledge states with reasons, the same vocabulary
   (`UNKNOWN`/`STALE`/`UNTRUSTED`/`INCOMPLETE`/`SYNTHETIC_CLOCK`), content-addressed
   evidence with sha256, idempotency on a stable identity, per-instance sequence
   state, and no trading controls anywhere. The disagreement is about wire shape
   and about two behaviours (gap handling, ordering), not about what monitoring
   means.

That makes this a reconcilable disagreement rather than a rebuild — but it is a
**decision**, and the stop rule reserves it to you.

## 7. Unresolved issues

1. **Which contract is canonical.** Four options are laid out in the
   compatibility report §9. LLS's is backed by a real producer, real captures and
   109 passing tests; ours has no producer. A translation layer looks tempting and
   would require inventing a `stale_after` that LLS never sends — the exact
   fabrication both contracts forbid.
2. **Sequence-gap behaviour is a direct conflict.** LLS expects `409` and retries
   until in-order; we accept and make the gap visible. A publisher built to retry
   forever against a receiver that already accepted is a live failure mode.
3. **Freshness models differ** (asserted state vs validity horizon). Both are
   defensible; combining them needs a deliberate answer, not a mapping table.
4. **`environment` is a different axis** on each side — market reality vs
   deployment tier. Our isolation boundary keys on a concept LLS does not send.
5. **No PostgreSQL available** for staging validation regardless of the contract.
6. Carried forward and still open: quarantine retention is unbounded; the shared
   gzip middleware decompresses without a byte ceiling.

## 8. Status summary

| Area | Result |
|---|---|
| Contract compatibility | **FAIL** — 0/19 fixtures accepted |
| Fixture compatibility | **FAIL** — harness cannot target the receiver |
| Canonical JSON | **PASS (algorithm) / FAIL (scope)** |
| PostgreSQL | **BLOCKED — NOT RUN** |
| Authentication | PARTIAL — synthetic only |
| Identity / idempotency | NOT RUN against LLS fixtures |
| Sequence handling | **CONFLICT** — 409-and-retry vs accept-and-record |
| Conflict handling | NOT RUN against LLS fixtures |
| Quarantine | NOT RUN against LLS fixtures |
| Recovery | NOT RUN |
| Security | PARTIAL — TLS untested |
| UI | NOT RUN against real evidence |
| Performance | **UNKNOWN — NOT MEASURED** |

---

## Decision

**BLOCKED — CONTRACT MISMATCH**

The receiver is not defective and the producer is not defective. They were built
to different contracts, and no amount of staging work resolves that. The next
step is a decision about which contract is canonical — not more testing.
