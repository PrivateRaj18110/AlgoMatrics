# monitoring.v1 receiver — test report

All figures are from actual runs on 2026-09-11/12. Nothing is projected.

---

## 1. Results

| Suite | Command | Result |
|---|---|---|
| **LLS acceptance harness** | `receiver_acceptance_test.py --endpoint …/api/monitoring/v1/messages` | **`{"status": "passed"}` — all 11 cases** |
| ops backend (full) | `.venv/Scripts/python.exe -m pytest -q` | **340 passed, 0 failed, 0 skipped** (15m03s) |
| platform backend | `PYTHONPATH=. uv run pytest tests/unit tests/architecture -q` | **452 passed, 2 failed** — both pre-existing, §4 |
| frontend | `npm run test` | **125 passed, 0 failed** (26 files) |
| frontend typecheck | `npx tsc -b` | clean |
| frontend lint | `npm run lint` | clean |
| ops lint (new files) | `ruff check --select F,E501,S608,W` | clean |
| migration | `alembic upgrade head` → `downgrade -1` → `upgrade head` | clean, SQLite |

### The external validation that matters most

The producer's own acceptance harness, **unmodified**, run against a live receiver process:

```json
{
  "status": "passed",
  "cases": [
    "duplicate_delivery_100",
    "identity_conflict_same_id_changed_body",
    "invalid_request_digest_header",
    "invalid_token",
    "malformed_and_oversized_rejection",
    "new_source_instance_sequence_starts_at_1",
    "out_of_order_1_3_2",
    "out_of_order_5_4_6_after_1_2_3",
    "sequence_gap",
    "unknown_stale_incomplete_synthetic_salvaged_preserved",
    "valid_four_message_sequence"
  ]
}
```

This is the difference between "our tests pass" and "the producer accepts us".

## 2. Test inventory

| File | Count | Covers |
|---|---|---|
| `ops/backend/tests/test_monitoring_v1_contract.py` | 42 | contract gate, canonical JSON, identity, limits, version policy, negative fixtures |
| `ops/backend/tests/test_monitoring_receiver.py` | 75 | the receiver capabilities, against real LLS fixtures |
| `tests/unit/test_monitoring_read_path.py` | 12 | platform read layer |
| `frontend/src/lib/monitoring.test.ts` | 14 | client model, freshness reading, environment |
| `frontend/src/components/monitoring/QualifiedValue.test.tsx` | 19 | rendering of every state |
| **Total** | **162** | |

## 3. Matrix coverage

### Contract

| Case | Covered |
|---|---|
| valid message | 19/19 producer-valid fixtures accepted |
| invalid schema | yes |
| unsupported version | quarantined, 422 |
| duplicate keys | rejected at parse, 400 |
| non-finite values | rejected at parse |
| invalid message ID | 400, identity mismatch |
| size / depth / node / string limits | 413 each |

### Authentication

| Case | Covered |
|---|---|
| valid credential | yes |
| invalid credential | 401 |
| foreign source | 403 |
| privilege escalation (publisher → admin) | 401 |
| cross-protocol (agent token) | 401 |
| expired credential | **NOT TESTED** — credentials are environment-variable based with no expiry mechanism |

### Identity, duplicate, sequence

| Case | Covered |
|---|---|
| first message | yes |
| duplicate | yes, one record |
| ACK-loss duplicate | yes, identical ACK identity |
| duplicate after later sequences | yes |
| changed body / invalid content address | 400 |
| expected sequence | yes |
| gap | 409, nothing stored |
| old sequence | 409 |
| out-of-order recovery (1-3-2 and 5-4-6) | yes |
| source-instance transition | yes |

### Evidence, quarantine, projection

| Case | Covered |
|---|---|
| append, immutability, update/delete rejection | yes |
| message stored verbatim, round-trips to producer bytes | yes |
| quarantine: malformed, unsupported, invalid identity | yes |
| quarantine not projected, admin-only, original bytes kept | yes |
| sequence refusal **not** quarantined | yes |
| projection per message type, supersession, rebuild, idempotent rebuild | yes |
| rebuild does not touch evidence | yes |

### Semantics

Every one covered: UNKNOWN, STALE, UNTRUSTED, INCOMPLETE, explicit null preserved, runtime array preserved, both environment axes separate, `source_as_of` verbatim, coverage verbatim, trust not upgraded, unrecognised states flagged rather than reinterpreted, no `stale_after` anywhere.

### Security

| Case | Covered |
|---|---|
| SQL injection (raw and schema-valid) | yes, exercised |
| hostile JSON, oversized input, malformed UTF-8, non-finite | yes |
| credential leakage in logs | yes |
| TLS | **NOT TESTED** |

### Transport

| Status | Covered |
|---|---|
| 200 accepted / duplicate | yes |
| 400 malformed, identity, digest | yes |
| 401 unauthenticated | yes |
| 403 foreign source | yes |
| 409 sequence | yes |
| 413 limits | yes |
| 422 version, schema | yes |
| 503 storage unavailable | yes |
| 429, 5xx, timeout, interrupted request | **NOT TESTED** |

### UI

| Case | Covered |
|---|---|
| all knowledge states render distinctly | yes |
| explicit null not shown as a value | yes |
| STALE not upgraded regardless of render time | yes |
| runtime array not collapsed | yes |
| coverage never shown as 0% or 100% when unstated | yes |
| unrecognised state shown unmodified | yes |
| historical continuity / page composition | **NOT TESTED** — components tested, page composition is not |

## 4. Pre-existing failures — classified with evidence

### `tests/unit/test_operations_integration.py::test_classification_contract_matches_f9bee1a`

**PRE-EXISTING.** `NON_TRADE_KINDS` gained `system_start` and `system_health` from the in-flight system-health work in the working tree (`operations/application/service.py` is uncommitted-modified). Nothing in this delivery touches classification.

### `tests/architecture/test_import_rules.py::test_cross_context_imports_use_public_facades`

**PRE-EXISTING.** The single violation is `modules/notifications/application/service.py → modules/operations/infrastructure/telemetry_store` — committed code, not modified here. Verified that the new `monitoring_store.py` is **not** implicated: a grep of the failure output for `monitoring_store` returns zero matches.

### `tests/unit/test_secrets_encrypted.py::test_cli_keygen_encrypt_decrypt`

**ENVIRONMENTAL / FLAKY.** Failed once in a full-suite run, then passed in isolation (6/6) and passed on a full-suite re-run (452 passed). This machine has known ACL problems with temp directories (see `windows-dev-environment`). Unrelated to monitoring — the file contains no reference to it.

## 5. The 61 skipped tests

**61 skipped → 75 executing, all passing.**

The superseded file was not deleted; it was rewritten in place against monitoring.v1 and the producer's fixtures. `test_capability_migration_is_complete` records the mapping of all 40 capability areas to their new test names and fails if any is missing.

Two capabilities no longer exist, documented in that test's docstring:

- **Conflict retention.** Needed a conflict table when identity was an opaque uuid. Under content addressing a changed body cannot keep a valid id, so the impostor is refused at validation and never becomes evidence.
- **Horizon-based staleness.** monitoring.v1 has no `stale_after`; the source asserts its own state. Guarded by `test_no_stale_after_anywhere_in_the_receiver_response`.

No assertion was weakened and no test was deleted to achieve green.

## 6. Not tested

| | |
|---|---|
| PostgreSQL | migration, insert, duplicate, sequence conflict, quarantine, projection, rebuild, restart, rollback, concurrency |
| Concurrency | racing deliveries for the same identity |
| Restart / recovery | receiver restart mid-flight, failure during persistence |
| Failure modes | database unavailable while configured, slow database, disk full |
| Load | every metric — see `STAGING_READINESS.md` |
| TLS | certificate validation, hostname validation, downgrade |
