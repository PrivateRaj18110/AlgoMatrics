# monitoring.v1 receiver — implementation

**Canonical contract:** [`schemas/monitoring-v1/`](../../schemas/monitoring-v1), owned by the LLS producer and copied verbatim. The receiver adapts; the contract does not.

---

## 1. Architecture

```
LLS producer
     │  HTTPS outbound only
     ▼
POST /api/monitoring/v1/messages        ops/backend
     │
     ├─ authentication          (upload-only credential, scoped to one source_id)
     ├─ request-size validation (1 MiB, post-decompression)
     ├─ strict JSON parsing     (duplicate keys and non-finite numbers rejected)
     ├─ structural limits       (depth 24, 30k nodes, 100 array items, 4k strings)
     ├─ version validation      (exact match; anything else quarantined)
     ├─ JSON Schema validation  (the producer's schema, unmodified)
     ├─ message identity        (content address recomputed, not trusted)
     ├─ sequence validation     (ordered acceptance; gap or old ⇒ 409)
     ├─ duplicate determination (by content address, before ordering)
     ├─ immutable evidence      (committed before the ACK)
     ├─ projection
     └─ monitoring.ack.v1
                │
                ▼
          PostgreSQL (SQLite in tests)
                │
                ▼
  platform API /api/v1/operations/monitoring/*
                │
                ▼
          frontend /app/lls-monitoring
```

There is no arrow back to LLS. No filesystem, database, process or API dependency in that direction, and no trading control anywhere in the surface.

## 2. Modules

| File | Responsibility |
|---|---|
| [`app/monitoring/contract.py`](../../ops/backend/app/monitoring/contract.py) | loads the canonical schema, version policy, canonical JSON, content address, request digest, strict parsing, normative limits |
| [`app/monitoring/sequence.py`](../../ops/backend/app/monitoring/sequence.py) | ordered-acceptance policy and refusal observability |
| [`app/monitoring/freshness.py`](../../ops/backend/app/monitoring/freshness.py) | **reads** the source's assertion; deliberately has no evaluator |
| [`app/monitoring/receiver.py`](../../ops/backend/app/monitoring/receiver.py) | the pipeline above |
| [`app/monitoring/projections.py`](../../ops/backend/app/monitoring/projections.py) | derived current view, rebuildable |
| [`app/monitoring/views.py`](../../ops/backend/app/monitoring/views.py) | read models, everything verbatim |
| [`app/api/routers/monitoring.py`](../../ops/backend/app/api/routers/monitoring.py) | ingress + read API |
| [`app/models/monitoring.py`](../../ops/backend/app/models/monitoring.py) | storage, shaped to the LLS envelope |

## 3. Two orderings that are load-bearing

**Duplicate is decided before the ordering rule.** The contract requires a previously accepted message to be acknowledged again even after later sequences have arrived. If ordering ran first, a legitimate redelivery would be refused as an old sequence and the producer would retry forever.

**Evidence is committed before the ACK is returned.** The producer deletes from its durable queue on a successful ACK, so acknowledging before the write is durable would lose data on a crash between the two.

## 4. Sequence — the behaviour that changed

| Situation | Result |
|---|---|
| First message of an unseen instance, sequence 1 | accepted |
| First message of an unseen instance, any other sequence | **409** |
| Next expected sequence | accepted |
| Sequence ahead of expected | **409**, last accepted state retained |
| Older sequence, unknown content address | **409** |
| Older sequence, known content address | `duplicate` ACK |

A refused message leaves **no evidence and no projection** — asserted by `test_refused_message_never_becomes_evidence_or_projection`.

Gap observability survives, separated from the acceptance decision: `refused_gap_count`, `refused_old_count` and a bounded `observed_gaps` log let an operator see out-of-order delivery without any refused message appearing as data.

## 5. Freshness — the model that was removed

monitoring.v1 has **no `stale_after`**. The producer asserts freshness as a state (`freshness.source`), derived from source validity and trust.

Removed from the monitoring.v1 path entirely: the `stale_after` columns, the horizon evaluator, the browser timer that re-evaluated it every second. `test_freshness_is_read_not_computed` asserts the evaluator has not returned; `test_no_stale_after_anywhere_in_the_receiver_response` asserts the string appears nowhere in a response.

An unrecognised freshness state is **preserved and flagged**, never downgraded to UNKNOWN and never read as healthy.

## 6. Two environments, never conflated

| | Meaning | Source |
|---|---|---|
| `source_environment` | market reality — `live_trading`, `offline_fixture`, `replay`, … | the producer |
| `receiver_deployment_environment` | our deployment tier — production / staging / … | `MONITORING_DEPLOYMENT_ENVIRONMENT` |

Neither is derived from the other. Unset receiver tier is `UNKNOWN`, never inferred from the message — the producer does not know where we run. Storage and queries are scoped by the receiver tier, so a staging observation cannot be loaded into a production response.

## 7. Runtime

`runtime` is an array of capture identifiers (`["historical-final/2503001"]`). Stored as the array, returned as the array, rendered as the list. It is never collapsed into LIVE / HISTORICAL / SIMULATED — the UI derives its live-vs-not treatment from `environment`, which is where the producer actually expresses it.

## 8. Identity and conflict

`message_id` is `mon1/` + SHA-256 of the canonical JSON with `message_id` removed. The receiver **recomputes and compares** rather than trusting the label.

This removed a whole subsystem: the previous design needed a conflict table because identity was an opaque uuid and a disagreement could only be found after storing both versions. Under content addressing a changed body cannot keep a valid id, so an impostor is refused at validation and never reaches evidence. `monitoring_conflicts` was dropped.

## 9. Storage

| Table | Role | Mutable |
|---|---|---|
| `monitoring_evidence` | every accepted message, verbatim | **no** (ORM-enforced) |
| `monitoring_sequence_state` | ordered-acceptance state + refusal counters | counters |
| `monitoring_quarantine` | messages refused as uninterpretable | no |
| `monitoring_raw_requests` | original bytes of refused requests | no |
| `monitoring_projections` | current view | yes — **safe to delete** |
| `monitoring_audit` | receiver-side security events | no |

`message_json` holds the accepted message exactly as sent, so nothing is lost merely because the receiver has no column for it, and every projection can be rebuilt.

Migration `b5e83a17c246` reshapes storage from the retired proposal. It drops and recreates, which is safe **only** because those tables were never deployed and never held a message — the ingress that would have written them returned 503 from the moment the contract was superseded. Once in staging, evidence becomes irreplaceable and any future reshaping must migrate rows.

## 10. Status

| | |
|---|---|
| **IMPLEMENTED** | every section above |
| **TESTED** | 117 backend tests against the producer's own fixtures; the LLS acceptance harness passes all 11 cases unmodified |
| **VERIFIED** | against SQLite through the shipped migration, and against a live receiver process |
| **NOT TESTED** | PostgreSQL, concurrency, restart mid-flight, slow/full storage |
| **NOT MEASURED** | every performance metric |
