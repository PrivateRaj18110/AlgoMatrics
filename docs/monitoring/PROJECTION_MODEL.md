# Projection model

```
RECEIVED EVIDENCE   →   CURRENT PROJECTION   →   API   →   UI
   immutable              derived, disposable
```

## 1. The rule

Evidence is append-only. A projection is a derived view that can be dropped and rebuilt at any time. A newer revision, a conflict, a state change or a UI change **never** rewrites evidence — they only move the projection.

This is what makes a projection bug recoverable instead of a permanent corruption of history.

Enforced, not merely intended: SQLAlchemy `before_update` and `before_delete` listeners on `MonitoringEvidence` raise `EvidenceIsImmutable`. `test_evidence_cannot_be_updated_or_deleted` asserts both. A projection bug, a replay, or a well-meaning "fix the timestamp" migration cannot rewrite what a source actually said.

## 2. Storage separation

| Table | Role | Mutable |
|---|---|---|
| `monitoring_evidence` | every accepted message, verbatim | **no** |
| `monitoring_raw_requests` | original bytes of requests producing quarantined material | no |
| `monitoring_quarantine` | messages that never entered a projection | no |
| `monitoring_conflicts` | contradictions, both sides recorded | `acknowledged` only |
| `monitoring_sequence_state` | per-instance delivery health | yes (counters) |
| `monitoring_projections` | current view | yes — **and safe to delete entirely** |
| `monitoring_audit` | receiver-side security events | no |

`monitoring_evidence.envelope_json` holds the accepted message as published. Every projection in the system can be discarded and rebuilt from it. The denormalised columns beside it (`sequence`, `revision`, `stale_after`, `content_hash`, …) exist purely so ordering, staleness and conflict detection do not require parsing JSON on every read — they are derived from the same envelope, never an independent source of truth.

## 3. Projection identity

The envelope's `entity` is preferred wherever present, because conflict and revision semantics are defined on it: keying the projection on anything else would let a restatement update a different row than the conflict was detected against.

With no `entity`, the key falls back to the field that already identifies the subject inside its own payload:

| kind | key |
|---|---|
| `core_status`, `coverage_report` | one row per (environment, source) |
| `feed_status` | `feed_id` |
| `processing_status` | `component` |
| `strategy_evaluation` | `strategy` + `instrument` |
| `risk_evaluation` | `order_id` or `signal_id` |
| `order_lifecycle` | `logical_order_id` |
| `fill` | `fill_id` |
| `position` | `account` + `instrument` + `authority` |
| `trade_timeline` | `trade_id` |
| `latency_summary` | `interval` + `scope` |
| `error` | `error_id` |
| `incident` | `incident_id` |
| `reconciliation` | `scope` + `subject` |

These are **routing decisions, not interpretations** — each names a field that already identifies the subject. An unkeyable observation becomes its own row (`message:<id>`) rather than silently overwriting an unrelated one.

`position` keys on `authority` deliberately: a Core-asserted position and a broker-reported position are different claims and occupy different rows. They are never merged into one number.

## 4. Ordering

1. Higher `revision` wins — the contract's restatement mechanism.
2. For a message naming an `entity`, equal revision means **the same position**, whatever the sequence numbers. Two different accounts of one entity revision are a conflict, and the order in which they happened to be sent does not make the later one correct.
3. For a message with no entity, revision carries no restatement meaning. Order by `sequence` within one publisher instance, and by `generated_at` across instances — sequence restarts when the instance does.

**Arrival order is never consulted.** `test_late_lower_revision_does_not_move_the_projection` delivers revisions backwards and asserts the projection holds the higher one.

## 5. Rebuild

`projections.rebuild(session)` deletes every projection row and replays `monitoring_evidence` in publisher order (`generated_at`, `source_instance`, `sequence`).

- `test_projections_rebuild_identically_from_evidence` asserts the rebuilt state matches the incrementally maintained one, across three incident revisions plus an unrelated feed status.
- `test_rebuild_does_not_touch_evidence` asserts the evidence row count is unchanged.

This is both the recovery path for a projection bug and the property test that keeps the evidence/projection split honest: if a rebuild cannot reproduce the current view, the view was holding something the evidence does not support.

## 6. Conflict and the projection

On conflict the projection does **not** move. It is flagged `has_conflict`, the `monitoring_conflicts` row records both sides, and the UI shows `DISPUTED`. A later revision supersedes the disputed one and clears the flag — the conflict record itself is never deleted, so the history of the disagreement survives.

## 7. Status

| | |
|---|---|
| **IMPLEMENTED** | evidence/projection separation, immutability enforcement, deterministic keying, contract ordering, rebuild |
| **TESTED** | rebuild equivalence, evidence immutability, out-of-order delivery, conflict non-resolution |
| **UNKNOWN** | rebuild cost at production evidence volume — `rebuild` loads and replays every row, which is fine at thousands and unproven at millions |
