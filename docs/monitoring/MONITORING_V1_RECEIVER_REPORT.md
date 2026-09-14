# monitoring.v1 receiver report

**Endpoint:** `POST /api/v1/monitoring/export` on ops-api
**Public path:** `https://<host>/ops/api/v1/monitoring/export` (nginx already proxies `/ops/api/` to ops-api; no nginx change was required)

---

## 1. Validation order

Implemented exactly as specified. Each stage runs before a message can become visible.

```
HTTP request
   ↓  router dependency: require_monitoring_publisher        401 / 403
authentication
   ↓  router: len(decompressed body) vs limit                413
transport-size validation
   ↓  receiver._ingest                                       400 + quarantined
JSON parsing
   ↓  contract.classify_version                              QUARANTINED
schema-version validation
   ↓  contract.envelope_validator                            QUARANTINED
JSON Schema validation
   ↓  source / environment scope, envelope size, integrity   REJECTED / QUARANTINED
message identity validation
   ↓  sequence.observe                                       recorded, never fatal
sequence validation
   ↓  evidence primary key                                   DUPLICATE
conflict / idempotency validation
   ↓  monitoring_evidence insert                             ACCEPTED
immutable evidence persistence
   ↓  projections.apply                                      CONFLICT if contradictory
projection
   ↓
API / UI
```

Nothing invalid reaches a projection. `test_unsupported_major_is_quarantined_not_rejected` asserts the projection count stays zero after a quarantined message.

## 2. Acknowledgement semantics

HTTP 200 means the batch was processed, not that every message was stored. The publisher must read `outcomes`.

| Status | Stored | Visible | Publisher action |
|---|---|---|---|
| `ACCEPTED` | yes | yes | delete from queue |
| `DUPLICATE` | already was | yes | delete from queue |
| `QUARANTINED` | yes, verbatim | no | delete from queue; resending will not help |
| `CONFLICT` | yes, both versions | yes, flagged | delete from queue |
| `REJECTED` | no | no | delete from queue **and alert** |
| `FAILED` | no | no | **keep and resend with the same `message_id`** |

`FAILED` is the only status meaning "send it again".

## 3. Idempotency

`message_id` is the only idempotency key, enforced in two places:

1. An explicit lookup before any write.
2. The primary key on `monitoring_evidence` — so even a concurrent double delivery cannot create two rows. The `IntegrityError` path returns `DUPLICATE`, not a failure.

`test_ack_loss_retry_returns_duplicate` covers the ack-loss case: the receiver stored the message, the publisher never saw the response and resent it, and the second delivery creates nothing.

## 4. Sequence and ordering

Sequence is tracked per `(source_id, source_instance)`.

- A gap records the missing range and is surfaced in the acknowledgement and on `/sources`. **It never rejects the message that revealed it** — doing so would destroy the evidence of the loss.
- A late arrival inside a known gap closes that range and increments `out_of_order_count`.
- A new `source_instance` starts a new row: that is a publisher restart, not data loss. `test_publisher_restart_is_not_data_loss` asserts `gap_count == 0` for both instances.

Arrival order is never consulted for ordering. Projections order by `revision`, then `sequence` within one instance, then `generated_at` across instances.

## 5. Conflict

Conflict semantics apply to messages that name an `entity` — that is where `revision` has restatement meaning. Same entity, same revision, different content hash ⇒ `CONFLICT`:

- both messages are retained as evidence
- the projection does **not** move
- the projection is flagged `has_conflict`
- a `monitoring_conflicts` row records both message ids, both content hashes and both generation times

Nothing auto-resolves. The API exposes no resolve action; `conflict_view` returns the literal `"resolution": "NOT_RESOLVED_BY_DASHBOARD"`.

For observations with no `entity` (a feed status every few seconds, for instance), successive messages are simply successive — treating them as conflicts would make every normal update a contradiction.

## 6. Version handling

| Received | Behaviour |
|---|---|
| `1.0` | validated strictly |
| `1.7` (newer minor) | unknown fields stripped **driven by the schema's own `additionalProperties` errors**, revalidated, publisher's version preserved in storage, `compatibility` reported in the ack |
| `2.0` (unsupported major) | `QUARANTINED`, original request bytes preserved |
| `v1`, missing, non-string | `QUARANTINED` — never inferred from payload shape |

The publisher's declared version is stored as sent, even when compatibility handling was applied to read the message.

## 7. Status

| | |
|---|---|
| **IMPLEMENTED** | every stage above |
| **TESTED** | 61 tests in `ops/backend/tests/test_monitoring_receiver.py`, all passing |
| **VERIFIED** | against SQLite through the shipped migration |
| **UNKNOWN** | concurrent-writer behaviour under PostgreSQL row locking; only the single-writer path is exercised |
| **NOT TESTED** | receiver restart mid-batch, disk-full, slow-database — see `TEST_REPORT.md` |
