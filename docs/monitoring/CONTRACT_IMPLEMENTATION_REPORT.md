# Contract implementation report — monitoring.v1

**Date:** 2026-09-11
**Scope:** the algomatric.in receiver and presentation side only. Nothing in the LLS repository was read, imported, or modified.

---

## 1. What the contract is

The canonical contract is [`schemas/monitoring-export/v1/`](superseded/monitoring-export-v1-proposal/v1) plus [`docs/DATA_CONTRACT.md`](superseded/monitoring-export-v1-proposal/DATA_CONTRACT.md) — both since archived under `superseded/`, because this proposal was replaced by the producer's canonical `monitoring.v1`. The paths named in the prose are the ones that existed when this was written. It was **not** redesigned for this work. The receiver loads those exact files at runtime — it does not vendor a copy — so the publisher and the receiver cannot drift by one side quietly editing its own version.

If the schemas cannot be loaded, the receiver returns 503 and accepts nothing. A receiver that cannot validate must not accept data.

Implementation: [`ops/backend/app/monitoring/contract.py`](../../ops/backend/app/monitoring/contract.py).

## 2. Where each contract clause landed

| Contract clause | Implementation | Test |
|---|---|---|
| Envelope shape | `contract.envelope_validator()` — the published schema, unmodified | `test_valid_message_is_accepted_and_projected` |
| Batch wrapper | `receiver._wrapper_validator()` — derived from the published batch schema with per-message validation deferred | `test_acknowledgement_reports_every_message_individually` |
| Per-message outcomes | `receiver.MessageOutcome`, six statuses | `test_acknowledgement_reports_every_message_individually` |
| `message_id` idempotency | primary key on `monitoring_evidence` + pre-check | `test_duplicate_delivery_creates_one_record` |
| `sequence` loss detection | `app/monitoring/sequence.py` | `test_sequence_gap_is_recorded_and_the_message_is_still_stored` |
| `revision` restatement | `projections._compare` | `test_higher_revision_supersedes_without_destroying_evidence` |
| Conflict | `monitoring_conflicts`, both versions retained | `test_same_entity_same_revision_different_content_is_a_conflict` |
| Qualified values | passed through verbatim end to end | `test_api_serialisation_preserves_every_qualified_state` |
| `freshness.stale_after` | `app/monitoring/freshness.py`, re-evaluated client-side | `test_dead_feed_becomes_stale_and_keeps_its_last_value` |
| Version policy | `contract.classify_version` | `test_unsupported_major_is_quarantined_not_rejected` |
| Forward minor compatibility | `contract.strip_unknown_fields`, schema-driven | `test_newer_minor_is_accepted_with_unknown_fields_ignored` |
| Integrity digest | `contract.content_digest` | `test_integrity_mismatch_is_quarantined` |
| Transport limits | router + receiver | `test_oversized_batch_is_rejected`, `test_compression_cannot_smuggle_an_oversized_body` |

## 3. One clarification the contract needed

`docs/DATA_CONTRACT.md` specified `integrity.digest` as *"Hex sha256 over the canonical JSON serialisation of `observation`"* without defining **canonical**. Publisher and receiver cannot agree on a digest without that definition, so the receiver pins it:

> UTF-8, object keys sorted, separators `,` and `:` with no insignificant whitespace, non-ASCII characters left unescaped.

Implemented as `contract.canonical_json`. This tightens an existing field's definition; it does not change the contract's meaning, add a field, or alter any semantics. **The publisher must use the same encoding or every integrity check will fail.** It is worth confirming with the LLS side before integrity checking is switched on — this is the one place where the two implementations could silently disagree.

No other change to the contract was made or is proposed.

## 4. What was deliberately not done

- **No second contract.** The `raj_monitor` agent `Envelope` was not extended, reused, or aliased. The two protocols have separate credentials, separate tables, separate validation and separate routes.
- **No reinterpretation.** The receiver does not compute coverage, determine root cause, infer timeline edges, or recompute latency. Those remain the Monitoring Backend's output, displayed as supplied.
- **No control surface.** One write route exists (`POST /export`) and it writes observations. Asserted structurally by `test_monitoring_routes_expose_no_control_actions` against the OpenAPI surface.

## 5. Status

| | |
|---|---|
| **IMPLEMENTED** | Full receiver pipeline, storage model, projections, read API, platform read path, UI representation |
| **TESTED** | 61 receiver tests + 46 contract tests + 32 frontend tests + 11 platform read-path tests, all passing locally |
| **VERIFIED** | Against SQLite via the shipped Alembic migration, and against the published schemas |
| **UNKNOWN** | Behaviour under real PostgreSQL at production volume — not exercised |
| **REQUIRES PRODUCTION ACCESS** | Any claim about deployment, TLS, DNS, or live publisher interoperability |
