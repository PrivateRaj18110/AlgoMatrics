# Quarantine report

## 1. Quarantine is not dead-lettering

The repository already had `ingest_dead_letters`. It is a different thing, and conflating them would lose information in both directions.

| | `ingest_dead_letters` | `monitoring_quarantine` |
|---|---|---|
| Protocol | `raj_monitor` agent | monitoring.v1 |
| Cause | an envelope that could not be **persisted** — malformed or unroutable, would fail identically on redelivery | a message that could not be **interpreted** — unsupported major version, failed integrity check, payload that does not satisfy the schema |
| Original bytes | no (truncated `payload_preview` only) | yes, in `monitoring_raw_requests` |
| Failure class | permanent persistence failure; transient failures deliberately never land here | semantic/version failure; the bytes may be perfectly valid to a future receiver |
| Recovery | none — the record is a debugging artefact | an unsupported major becomes readable once the receiver implements that major |

The distinction that matters: a dead letter is something we understood and could not store. A quarantined message is something we stored and could not understand. The second is recoverable; the first generally is not.

## 2. What quarantine preserves

`monitoring_quarantine` (one row per quarantined message):

- `quarantine_id`, `request_id`, `batch_index` — locates the message inside the preserved request
- `message_id`, `schema_version`, `environment` — **only where extractable**; a message may be quarantined precisely because its version could not be read, and those fields are then NULL rather than guessed
- `source_id` — the **authenticated** source, not the one claimed in the body. When a request is quarantined because its body is untrustworthy, the credential is the only identity worth recording
- `reason` (stable machine-readable code), `detail` (human-readable)
- `integrity_algorithm`, `integrity_digest` — what was claimed, when the claim failed
- `received_at`

`monitoring_raw_requests` (one row per request that produced quarantined material):

- `body` — the original bytes, stored **post-decompression and pre-parse**, the last point at which they are still exactly what the publisher sent
- `body_sha256`, `byte_length`, `content_encoding`
- `claimed_source_id` alongside the authenticated `source_id`

Raw bodies are kept only when something in the request could not be interpreted. Storing every accepted body would double storage for no forensic gain: accepted messages are already recoverable verbatim from `monitoring_evidence.envelope_json`.

## 3. Reasons currently emitted

| Reason | Stage | Raw bytes kept |
|---|---|---|
| `batch_unparseable` | JSON parsing | yes |
| `batch_not_an_object` | JSON parsing | yes |
| `batch_schema_invalid` | batch wrapper validation | yes |
| `schema_version_missing` | version classification | yes |
| `schema_version_malformed` | version classification | yes |
| `schema_major_unsupported` | version classification | yes |
| `schema_invalid` | envelope validation | yes |
| `integrity_mismatch` | integrity check | yes |

## 4. Quarantined material never becomes monitoring data

- It never enters `monitoring_projections`. `test_unsupported_major_is_quarantined_not_rejected` asserts the projection count stays zero.
- `/api/v1/monitoring/quarantine` requires a **separate administrative credential** (`MONITORING_ADMIN_TOKEN`). A dashboard viewer cannot see it, and neither can a publisher: `test_publisher_credential_grants_no_administrative_access` asserts a publish token gets 401 there.
- Presenting unreadable material next to validated monitoring data would give it a credibility it has not earned.

## 5. A 4xx still leaves a record

Transport-level rejections (`400` unparseable, `413` oversized, `403` wrong source) are reported to the publisher as errors, **and** the quarantine row, the preserved bytes and the audit entry are committed before the error is raised.

This required an explicit commit-then-raise in `receiver.ingest_batch`: the natural `rollback()` on exception would have left a refused upload with no record that it ever happened. `test_malformed_json_is_a_400_and_is_preserved` asserts the exact original bytes survive a 400.

## 6. Retention

**Not implemented.** There is no retention or pruning job for `monitoring_quarantine` or `monitoring_raw_requests`. Both grow without bound under a persistently misbehaving publisher.

A publisher stuck on an unsupported major version sending 1000-message batches would grow `monitoring_raw_requests` by one full request body per request. This is a real operational exposure and it is listed as an open item in `PRODUCTION_READINESS.md`. The existing ops retention settings (`dead_letter_retention_days` and friends) are the pattern to follow, but no equivalent was added here.

## 7. Status

| | |
|---|---|
| **IMPLEMENTED** | quarantine tables, all eight reasons, raw-byte preservation, admin-only access, commit-on-4xx |
| **TESTED** | unsupported major, malformed JSON, schema-invalid payload, integrity mismatch, admin access control |
| **VERIFIED** | original bytes recovered byte-for-byte after a 400 |
| **NOT IMPLEMENTED** | retention / pruning — unbounded growth under a misbehaving publisher |
| **NOT IMPLEMENTED** | release-from-quarantine (re-processing a message once its major becomes supported) |
