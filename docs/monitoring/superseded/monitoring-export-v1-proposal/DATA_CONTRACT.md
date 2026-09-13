> **SUPERSEDED — this is not the contract.**
>
> This document described `monitoring-export/v1`, a receiver-side proposal
> written before the LLS producer contract was available. It was retired on
> 2026-09-11 when the canonical LLS `monitoring.v1` contract arrived; 0 of 19
> producer-valid fixtures validated against the schemas described here.
>
> The canonical contract is [`schemas/monitoring-v1/`](../../../../schemas/monitoring-v1).
> See [LLS_CONTRACT_RECONCILIATION.md](../../LLS_CONTRACT_RECONCILIATION.md).
>
> Kept because its reasoning about evidence immutability, quarantine, conflict
> retention and qualified values carried over to the canonical implementation.

# LLS Monitoring Export v1 — data contract

The versioned interface between the **LLS Monitoring Backend** (publisher) and
**algomatric.in** (receiver).

This document and the JSON Schemas in [`schemas/monitoring-export/v1/`](v1)
are the *entire* coupling between the two systems. Neither side imports code
from the other. LLS has no inbound route from here; algomatric.in has no
database, filesystem, process or broker connection into LLS. If a dashboard
requirement appears to need one, the requirement gets reported — not the
dependency created.

```
LLS Monitoring Backend
        │  HTTPS, authenticated, outbound-only
        ▼
POST https://algomatric.in/ops/api/v1/monitoring/export
        │
   ingestion → validation → algomatric-owned storage → projections → UI
```

---

## 1. The one idea

Everything else in this contract follows from a single rule:

> **A monitored value is never a bare scalar.**

Every exported value is a *qualified value* carrying an explicit knowledge
state. There is no way to write "0 incidents" on the wire when the truth is
"the incident engine is down and I cannot tell you". The schema rejects it:

```json
{ "state": "UNKNOWN", "value": 0 }        // rejected — UNKNOWN carries no value
{ "state": "UNKNOWN", "reason": "..." }   // accepted
```

This is deliberate. A dashboard that silently renders unknown as zero is worse
than no dashboard, because it manufactures confidence. Making the collapse
*unrepresentable* means no amount of downstream carelessness can reintroduce it.

---

## 2. Transport

| | |
|---|---|
| **Endpoint** | `POST /api/v1/monitoring/export` |
| **Body** | [`batch.schema.json`](v1/batch.schema.json) |
| **Response** | [`ack.schema.json`](v1/ack.schema.json) |
| **Direction** | Outbound from LLS only. The dashboard never initiates a connection to LLS. |
| **Encoding** | `application/json`, UTF-8. `Content-Encoding: gzip` supported. |

### Headers

| Header | Required | Meaning |
|---|---|---|
| `Authorization: Bearer <token>` | yes | Service credential, scoped to one `source_id` |
| `Content-Type: application/json` | yes | |
| `Content-Encoding: gzip` | no | Decompressed before size limits are applied |
| `X-Request-Id` | no | Echoed in logs for tracing |

Credentials are never committed to source. They support rotation, revocation
and expiry; every ingestion attempt is audited; rate limits apply per
`source_id`. The upload identity is **not** an administrative identity and
carries no read scope over other sources' data.

### Limits

| Limit | Value | On breach |
|---|---|---|
| Batch items | 1000 | `413` |
| Decompressed body | 8 MiB | `413` |
| Single envelope | 256 KiB | that envelope is `REJECTED`, the batch continues |

### Status codes

| Code | Meaning | Publisher must |
|---|---|---|
| `200` | Batch handled — **read `outcomes`** | act per-message (below) |
| `400` | Batch wrapper itself unparseable | fix and alert; do not spin |
| `401` | Missing/invalid credential | keep the queue, alert |
| `403` | Credential not scoped to this `source_id` | keep the queue, alert |
| `413` | Over a transport limit | split the batch and retry |
| `429` | Rate limited — honour `Retry-After` | keep the queue, back off |
| `503` | Receiver cannot store right now | keep the queue, retry with backoff |

> **`200` is not an acknowledgement of delivery.** It says the batch was
> processed, not that every message was stored. A publisher that deletes a batch
> from its outbound queue on the strength of the status code alone will lose
> data. Read `outcomes`.

---

## 3. Per-message outcomes

The acknowledgement returns one entry per message, including accepted ones, so
the publisher can reconcile its queue without inference.

| Status | Stored? | Visible? | Publisher action |
|---|---|---|---|
| `ACCEPTED` | yes | yes | delete from queue |
| `DUPLICATE` | already was | yes | delete from queue — nothing was written twice |
| `QUARANTINED` | yes, verbatim | no | delete from queue; resending will not change the outcome |
| `CONFLICT` | yes, both versions | yes, as a conflict | delete from queue |
| `REJECTED` | no | no | delete from queue **and alert** — retrying fails identically |
| `FAILED` | **no** | no | **keep in queue, resend with the same `message_id`** |

`FAILED` is the only status that means "send it again". Everything else is
terminal, and every terminal status leaves the data durable on the dashboard
side or explains why it could not be.

---

## 4. Envelope

Identity, ordering and timing live on the envelope; the monitored facts live in
the observation. The split lets the receiver decide idempotency, ordering and
conflict without interpreting a single trading fact.

```json
{
  "schema_version": "1.0",
  "message_id": "6f1c1e2a-6d9a-4f2b-9a3e-2b7c5d4e8f01",
  "source_id": "lls-monitoring-prod",
  "source_instance": "lls-mon-01-run-4412",
  "sequence": 90211,
  "revision": 0,
  "entity": { "type": "order", "id": "ORD-88213" },
  "generated_at": "2026-09-11T09:31:02.441Z",
  "source_time":  "2026-09-11T09:31:02.118Z",
  "data_as_of":   "2026-09-11T09:31:02.118Z",
  "runtime": "LIVE",
  "environment": "production",
  "observation": { "kind": "...", "qualifiers": { ... }, "payload": { ... } }
}
```

### Identity and idempotency

`message_id` is assigned **once** by the publisher and reused verbatim on every
retransmission. It is the only idempotency key. Redelivery must never produce a
second event, trade, fill, incident or metric.

> A retry that mints a fresh `message_id` is a contract violation and will
> duplicate data. Assign the id when the message is created, not when it is sent.

### Ordering

`sequence` is monotonic per `(source_id, source_instance)`, and resets to 0 when
`source_instance` changes — which is how the receiver distinguishes a publisher
restart from data loss.

Arrival order is never assumed to match source order. The receiver orders by
`sequence` and the qualified timestamps. A sequence gap is **recorded and
displayed**, never a reason to reject a message. Where ordering cannot be
safely resolved, the UI shows the uncertainty rather than inventing an order.

### Restatement and conflict

A later `revision` of the same `entity` supersedes an earlier one *for display*.
The earlier one is retained as received evidence — a projection never overwrites
the evidence it was built from.

Two messages naming the same `entity` at the same `revision` with different
content are a **conflict**. Both are kept, the conflict is recorded with both
sources, versions, timestamps and identities, and it is surfaced in the UI.
Nothing is silently overwritten and nothing is auto-resolved.

### Runtime and environment

`runtime` is one of `LIVE`, `SIMULATED`, `HISTORICAL`, `REPLAY`, `UNKNOWN`, and
must be labelled as such everywhere it appears. Simulated data presented as live
is precisely the failure this field exists to prevent. `environment` keeps
production and staging strictly separated in storage and in every view.

---

## 5. Qualified values

Defined in [`qualifiers.schema.json`](v1/qualifiers.schema.json).

| State | Carries a value? | Means |
|---|---|---|
| `KNOWN` | required | Observed, current, trusted |
| `UNKNOWN` | **forbidden** | The source cannot say |
| `STALE` | required (+ `as_of`) | Was known; past its validity point |
| `UNTRUSTED` | required | Exists, but the source does not vouch for it |
| `INCOMPLETE` | optional | Partial — some contributing inputs missing |
| `UNSUPPORTED` | **forbidden** | This build cannot produce the field at all |
| `NOT_APPLICABLE` | **forbidden** | No meaning in this context |
| `SIMULATED` | required | Produced by simulation, not observation |
| `SYNTHETIC_CLOCK` | required | Produced under an artificial clock |

Each state has its own UI representation. They are not interchangeable:
`UNSUPPORTED` ("this build never reports it") and `UNKNOWN` ("it should report
it and cannot") lead to different operator actions, and `NOT_APPLICABLE`
("unfilled orders have no fill price") is not a gap at all.

`source_state` preserves LLS's own raw token unmapped, so a forensic view can
show what the source actually said even after normalisation.

### Every observation carries qualifiers

```json
"qualifiers": {
  "freshness":  { "data_as_of": "...", "stale_after": "...", "state": "FRESH" },
  "trust":      { "level": "AUTHORITATIVE", "basis": "..." },
  "coverage":   { "ratio": { "state": "KNOWN", "value": 0.82 } },
  "provenance": { "derivation": "OBSERVED", "authority": "CORE_ASSERTED" },
  "clock":      { "domain": "CORE_WALL", "quality": "DISCIPLINED" }
}
```

`freshness`, `trust` and `provenance` are mandatory. An observation that cannot
say how fresh or how trusted it is cannot be displayed honestly.

---

## 6. Time

Five distinct instants, never conflated:

| Instant | Set by | Field |
|---|---|---|
| Source time | LLS, in its own clock domain | `source_time` |
| Generation time | Monitoring Backend | `generated_at` |
| Validity point | Monitoring Backend | `data_as_of` / `freshness.data_as_of` |
| Receipt time | **algomatric.in** | stamped on ingest, returned as `received_at` |
| Display time | the browser | computed at render |

A delayed dashboard must never look live. Every panel can answer: when was this
generated, when was it received, what is it valid as of, is it stale, is the
source healthy, is the data complete.

### Staleness is the source's call

`freshness.stale_after` is supplied by LLS. After that instant the dashboard
**must** present the payload as `STALE / LAST UPDATE: <time>`, whether or not
newer data has arrived. The dashboard does not invent a staleness policy, and it
does not decide something is still fresh because it looks recent.

If updates stop, the last valid state continues to be shown — clearly marked
stale, never as if it were current.

### Clock domains

`clock.domain` and `clock.quality` say which clock a timestamp came from and how
much the source trusts it. Latency is **never** computed here by subtracting two
timestamps: only LLS knows which pairs share a domain. Intervals arrive
pre-computed, with `clock_quality` attached so a distribution built on a degraded
clock is labelled rather than read as fact.

---

## 7. Observation kinds

Defined in [`observations.schema.json`](v1/observations.schema.json).

| `kind` | Feeds | Notes |
|---|---|---|
| `core_status` | Executive page | Health verdicts **supplied by** Monitoring; the dashboard forms none of its own |
| `feed_status` | Feed dashboard | Connection state, gaps, reconnects, rates, authority |
| `processing_status` | Processing dashboard | received / parsed / normalized / accepted, errors, telemetry gaps |
| `strategy_evaluation` | Strategy dashboard | Observational only — no parameters or thresholds exist in the contract |
| `risk_evaluation` | Risk dashboard | Decisions and latency; read-only |
| `order_lifecycle` | Orders page | Logical / physical / broker identities kept **separate** |
| `fill` | Fills | `authority` mandatory |
| `position` | Positions | One claim per authority; never merged |
| `trade_timeline` | End-to-end timeline | Nodes, established edges, and named `missing_stages` |
| `latency_summary` | Latency dashboard | Pre-computed p50/p95/p99/max + sample/missing/excluded counts |
| `error` | Error dashboard | A thing that happened |
| `incident` | Incident dashboard | A judgement about impact; revisions retained |
| `reconciliation` | Reconciliation dashboard | `CONSISTENT`/`PENDING_LAG`/`MISMATCH`/`CONFLICTING`/`UNKNOWN` |
| `coverage_report` | Coverage dashboard | Only figures LLS actually asserted |

Values the dashboard must reason about structurally (severity, reconciliation
state, latency interval names) are closed enums. Values belonging to LLS's own
vocabulary (order state, strategy state, feed state) are qualified strings with
the source token preserved — so `DEGRADED_FEED_ONLY` does not quietly become
`degraded`.

### Three things the contract deliberately does not let the dashboard do

- **Derive coverage.** `coverage.ratio` is supplied. Given `observed` and
  `expected` and no ratio, the ratio stays `UNKNOWN`. A percentage the source
  did not assert is a fabricated percentage.
- **Determine root cause.** `incident.root_event` is optional and carries its own
  trust. Absent means LLS has not determined one — a plausible-looking first
  error is never promoted to a cause.
- **Manufacture timeline edges.** Only established edges are exported. A missing
  stage is listed in `missing_stages` and rendered as a named hole, not bridged
  because two known stages happen to be adjacent in the canonical order.

`UNKNOWN` reconciliation is not `CONSISTENT`. Not being able to check is not a pass.

---

## 8. Version compatibility

`schema_version` is `major.minor` and is never inferred from payload shape.

| Received | Receiver behaviour |
|---|---|
| Same major, same/older minor | Accept and validate normally |
| Same major, **newer** minor | Accept; ignore unknown fields; preserve the source version; record that compatibility handling was applied; report it in `ack.compatibility` |
| **Unsupported major** | `QUARANTINED` — stored verbatim, not projected to any view, retrievable by an administrator |
| Unparseable / integrity mismatch | `QUARANTINED` or `REJECTED`, never repaired |

Semantic data is never silently repaired and never guessed at.

> The published schemas are a *precise description* of 1.x, not a permissive
> filter: they reject unknown fields. Forward compatibility with a future minor
> version is a **receiver behaviour** — strip unknown fields, validate the
> remainder, record the handling — not a loosening of the schema.

LLS can publish a v2 without the dashboard importing any LLS code: add
`schemas/monitoring-export/v2/`, implement the receiver, and both versions run
side by side until the publisher cuts over.

---

## 9. Receiver obligations

algomatric.in guarantees, and is tested on:

1. **Validate before visible.** Nothing reaches a projection unvalidated.
2. **Preserve evidence.** The received message is retained in its original form.
   A projection never overwrites the evidence it was built from, and evidence is
   never altered.
3. **Idempotency.** Same `message_id` twice produces one record.
4. **No reinterpretation.** Interpretation, correlation, reconstruction, derived
   metrics, incident logic, latency and source qualification are LLS's
   responsibility. The dashboard represents the supplied result.
5. **No trading capability.** No order placement, cancel, modify, resubmit,
   flatten; no strategy, risk, sizing or broker changes; no Core start/stop/
   restart. Read-only, structurally.
6. **Failure isolation.** If the dashboard, its storage or its network fails, LLS
   is unaffected — it is not in the trading path, and backpressure is never
   propagated to the publisher.
7. **Independent history.** An LLS failure cannot corrupt history already stored
   here.

The layering is strict and one-directional:

```
RECEIVED  →  VALIDATED  →  CURRENT PROJECTION  →  UI VIEW
```

---

## 10. Publisher obligations

1. Assign `message_id` once, at creation; reuse it on every retry.
2. Keep `sequence` monotonic per `source_instance`; change `source_instance` on
   restart.
3. Read `outcomes`; resend only `FAILED`.
4. Queue durably, and keep the queue on `401`/`403`/`413`/`429`/`503`.
5. Never downgrade a value's knowledge state to make a panel look better. A
   value the backend cannot vouch for goes out as `UNTRUSTED` or `UNKNOWN`.
6. Export `stale_after` wherever an observation has a validity horizon.
7. Never export a value LLS did not compute — no placeholder ratios, no
   zero-filled counters, no assumed root causes.

---

## 11. Validation

The schemas are executable. `ops/backend/tests/test_monitoring_export_contract.py` (removed with this proposal)
validates them directly — 46 checks covering valid messages, missing fields,
unknown fields, invalid enums, oversized batches, version compatibility, the
knowledge-state rules, and a structural guard that fails the build if any field
name in the contract ever starts to read like a control.

```bash
cd ops/backend && python -m pytest tests/test_monitoring_export_contract.py -q
```

Publisher-side validation needs no dashboard code — any JSON Schema 2020-12
validator against `envelope.schema.json` is sufficient.

---

## 12. Changing this contract

| Change | Version bump |
|---|---|
| New optional field | minor |
| New `kind` | minor |
| New enum member the receiver can ignore | minor |
| New **required** field | **major** |
| Removing or renaming a field | **major** |
| Narrowing a type or enum | **major** |
| Changing the meaning of an existing field | **major** |

Every change updates the schemas, this document, and the contract tests in the
same commit. Published versions are never edited in place — a shipped publisher
is validating against them.
