# LLS Monitoring Export — monitoring.v1

**IMPLEMENTED. External data contract only.** LLS owns production of these messages. The receiver can implement this document and the [JSON Schema](../../../monitoring/export/monitoring.v1.schema.json) independently. No Algomatric source code, shared package, database, filesystem, frontend or deployment knowledge is required. No public destination has been contacted in this task.

## Direction, endpoint and authorization

An observer process sends `POST https://algomatric.in/api/monitoring/v1/messages`. This is a proposed receiver endpoint for the separate application to implement; it is not evidence that the public endpoint exists. LLS exposes no trading command in this contract. The website initiates no connection into Core.

Required headers are `Content-Type: application/json`, `Authorization: Bearer <upload-only-token>`, `Idempotency-Key: <message_id>` and `X-Monitoring-SHA256: <sha256-of-request-bytes>`. A token only authorizes ingestion of monitoring data for an explicitly allowed source. It grants no read, broker, order, configuration or Core process-control permission. The receiver must validate the token, source ID and registered source instance.

TLS validates certificate chain and configured hostname. The sender requires an exact configured HTTPS host and the endpoint path above, forbids userinfo/query/fragment, refuses redirects, and does not inherit proxy settings. The default host is `algomatric.in`; loopback test hosts are explicitly configured in fixtures. A port may be configured explicitly. Production should restrict observer egress to the approved receiving service through its host firewall.

Credentials are external `BBEXPORTCREDENTIAL1` JSON: `schema_version`, `token` (32–256 printable ASCII characters), and a timezone-qualified `expires_at`. Store the file with service-only read access. The sender rereads it for every attempt, so replacing the credential file rotates credentials without changing message identity. Expired/invalid credentials are refused before network activity. Never put credentials in worklists, URLs, source control or command arguments. Local sender validation does not replace receiver expiry/revocation checks.

## Envelope

| Field | Meaning |
|---|---|
| `schema_version` | Exact `monitoring.v1`. Independent of raw/canonical/report versions. |
| `message_id` | `mon1/` followed by the SHA-256 of the canonical envelope excluding `message_id`. Stable for every retry. |
| `message_type` | `monitoring.snapshot`, `monitoring.events`, `monitoring.incidents`, or `monitoring.forensic_reference`. |
| `source_id` | Registered logical source; 1–80 ASCII letters/digits/underscore/dot/hyphen. |
| `source_instance` | Registered observer epoch, not a Core process ID. Never reuse an instance with a reset sequence. |
| `source_sequence` | Positive decimal string, less than 2^63. Increasing within the source/instance pair. |
| `generated_at` | Observer export derivation time, timezone-qualified UTC ISO-8601. Not market or broker time. |
| `source_as_of` | Observer acquisition ns, a qualified source time or explicit unknown object, and validity meaning. Current source cuts are per object; no common qualified source clock is available. |
| `runtime` | Bounded source-scoped runtime references. Empty means identity unavailable, not evidence that no runtime exists. |
| `environment` | Explicit capture mode: offline fixture, replay, offline live shaped, live market paper, broker sandbox, live trading, or unknown. No mode declaration alone qualifies a clock or proves live health. |
| `coverage` | Knowledge of the evidence population. Current complete-session coverage remains `INCOMPLETE`, with capture status and reason. |
| `freshness` | Source freshness and reason, plus monitoring derivation time. Receipt time cannot upgrade historical evidence to live. |
| `trust` | Observation authority and its scope. Current observations are source assertions and observer derivations; independent broker trust remains UNKNOWN. |
| `payload` | Explicit, type-specific projection described below. Not a serialized database or internal report. |

Canonical JSON uses UTF-8, sorted object keys, compact separators, no ASCII escaping of non-ASCII characters, and no NaN/infinity. Duplicate keys are invalid. Canonicalization and the identity digest are specified by the supplied producer tests and examples. `X-Monitoring-SHA256` covers exact transmitted bytes, including `message_id`, and is distinct from the message-ID digest.

Monetary/price quantities are decimal strings in source micros. Currency and contract metadata remain unqualified unless evidence provides them. Large sequence/identity integers are decimal strings. Population counts bounded by the schema may be JSON integers. A zero observed count is a statement about the imported population, not proof that an activity never occurred outside coverage.

## Payloads

`monitoring.snapshot` has exactly: `capture_ref`, `definition`, `system`, `feed`, `processing`, `strategy`, `risk`, `execution`, `orders`, `fills`, `positions`, `pnl`, `latency`, `errors`, `incidents`, `reconciliation`, `observer`, `evidence`.

The projection contains source-cut assertions, bounded physical-order/local-fill/position summaries, feed counter deltas, evaluation/signal counts, rejection/submission rates with denominators, qualified timing summaries and exclusions, error/incident summaries, reconciliation statuses and artifact digest references. It excludes raw source words, source paths, SQL rows, credentials and unrestricted history. Snapshot sections are replacements of a described population, never additive economic transactions. Lists carry `available`, `exported` and `truncated`; omission due to a limit is not zero state.

`monitoring.events` has `capture_ref`, at most 100 `items`, `offset`, `available`, `next_offset` and `order`. Each event carries the existing taxonomy, stable evidence ID, component, original source sequence and clock meaning, evidence reference and knowledge classification. Ordering is within artifact role and source sequence, not global causality. Page offsets are tied to an immutable capture and projection version. Request additional pages as separate immutable messages; no unlimited history request is supported.

`monitoring.incidents` has `capture_ref`, at most 100 revision items, `offset`, `available` and `next_offset`. A revision retains incident ID, revision, prior digest, severity, trust, actor/action, rule version, evidence, recovery and delivery state. Source timestamps, cause and impact remain unknown if unsupported. Revisions append; a receiver must not erase prior history when applying a newer revision. Disappearance from a bounded snapshot does not resolve an incident.

`monitoring.forensic_reference` has `case_id`, `sha256`, `bytes`, `coverage` and `retrieval`. It references an explicitly generated bounded `BBCASE1` bundle retained by LLS. Current retrieval is `operator_approved_transfer`; there is no arbitrary path, Core filesystem route or public raw-evidence download endpoint. The message itself does not authorize transfer of the ZIP.

P0/P1/P2 describe retention/importance, never alert severity. Current LLSP decision/economic/error/custody records are P0, continuous market/processing records P1, and `FEED_STATUS_OBSERVED` samples P2. Available event references do not invent missing native events.

## Unknown, trust and timing

An unavailable fact is represented explicitly, for example `{"value":null,"status":"UNKNOWN","reason":"full_risk_and_sizing_state_not_exported"}`. Preserve distinctions between UNKNOWN, UNSUPPORTED, N/A, STALE, INCOMPLETE, UNTRUSTED, SIMULATED and SYNTHETIC_CLOCK. Never replace them with false, zero, healthy or flat. Enum spellings in existing referenced evidence are preserved; clients must not reinterpret an unfamiliar value as healthy.

Every source timestamp retains its domain, clock identity, boundary, provenance, precision and uncertainty when exported. Synthetic/offline/caller labels cannot enter qualified production latency distributions. Missing/incompatible endpoints remain unknown with exclusions. Current P99.9 requires at least 1,000 qualified samples; this is an empirical sample floor, not a statistical confidence guarantee. Current source evidence does not establish the full qualified feed-to-position chain.

Sealed framing and complete session coverage are distinct. Salvaged captures remain labeled `salvaged`; their BBSALV1 classification may be SEALED_VALID, UNSEALED_SALVAGEABLE, UNSEALED_PARTIAL, CORRUPT, TRUNCATED, UNSUPPORTED or INVALID. A corrupt tail never makes verified prefix records complete-session evidence. Receiver freshness must use source validity and trust, not merely arrival or publication time. Current exported Core health remains UNKNOWN.

## Idempotency, ordering and acknowledgements

Delivery is **at least once**. LLS persists exact bytes before attempting transmission and retries the same file, ID, sequence and digest after an uncertain acknowledgement. The receiver must atomically retain accepted identity/digest and its sequence before acknowledging. Duplicate identity and identical digest must return `duplicate` with the same identity. Reuse with different bytes is a conflict; do not overwrite previously accepted data or add another economic fill.

Sequences are scoped to `(source_id, source_instance)`. Expect 1 first and then the next sequence. A previously accepted duplicate can be acknowledged again after later sequences. Reject an unknown older sequence or gap with 409; retain the last accepted state. A receiver restart must preserve deduplication and ordering metadata. Resynchronization and new source-instance registration are explicit operational steps, not silent sequence resets. Do not accumulate fill economics from repeated snapshots or from different observation captures.

A successful 200/201 response has exactly:

```json
{
  "schema_version": "monitoring.ack.v1",
  "message_id": "mon1/<same-message-digest>",
  "sha256": "<exact-request-byte-digest>",
  "source_sequence": "1",
  "status": "accepted"
}
```

`status` may also be `duplicate`. The sender checks all identities and never treats an empty body, malformed JSON, duplicate keys, wrong schema, wrong sequence or mismatched digest as success. ACK bodies are capped at 4,096 bytes. ACK loss after commit is an uncertain result, so the exact message is retried. A scoped OS delivery-owner lock serializes attempts for each source instance without holding the evidence writer lock during network activity.

## Errors, retry and limits

| Outcome | LLS behavior |
|---|---|
| DNS/TCP/TLS failure, reset, timeout, invalid ACK | Retain pending message and retry with stable identity. |
| 408, 425, 429, 5xx | Retry with bounded exponential backoff. |
| Other 4xx, including 401/403/409/413 | Retain blocked delivery; expose error; retry slowly after 900 seconds so explicit credential/receiver repairs can take effect. |
| Success with validated identity | Append acknowledged delivery revision; proceed to the next sequence. |
| Exhausted attempts or capacity | Mark degraded and retain evidence; require operator intervention. Never backpressure Core. |

Defaults: 1 MiB request, 100 entries per array/page, 24 nesting levels, 30,000 nodes, 4,096 characters per string, 256 retained outbox messages, at most 100 attempts per message. Worklists contain at most 256 paths and the service retains at most 1,000 jobs. One oldest pending delivery attempt per service cycle; the default cycle interval is 30 seconds and minimum is 10. Retry delay starts at 10 seconds, doubles and caps at 900 seconds. Outbox capacity includes acknowledged messages until an approved archival/retention process is introduced; there is no automatic deletion.

The sender runs network work in an owned subprocess with a 10-second whole-attempt deadline (maximum 15), in addition to socket timeouts. Deadline termination can make an ACK uncertain; identity is retained. Collection, evidence and analytics remain local when the destination is unavailable. Disk exhaustion refuses observer work without changing trading behavior. These bounds are independent from the Core.

## Compatibility and change control

The version identifies field meaning, not just shape. This producer rejects unknown top-level fields, unknown message types and schema versions. Breaking field meaning, identity, ordering or mandatory-field changes require `monitoring.v2`. Receivers must quarantine unsupported versions, not guess. Additive changes require a documented schema revision and compatibility test before use; do not silently relax the current strict schema. Maintain v1 alongside v2 for an agreed migration interval and publish a dated deprecation decision before retiring v1. No retirement date is currently set.

The older local BBVIEW1 dashboard experiment is historical compatibility code. It is not this external contract and is not used by the current `monitoring.runtime` command. The Core publisher is superseded and not approved; this contract is produced entirely after Black Box ingestion.
