# Algomatric monitoring.v1 contract fixture package

This directory is a standalone handoff package for an independent receiver. It
does not require the LLS source tree, LLS imports, LLS databases, Core files,
broker access or Algomatric code.

The receiver endpoint under test is:

```text
POST /api/monitoring/v1/messages
Content-Type: application/json
Authorization: Bearer <upload-only-token>
Idempotency-Key: <message_id>
X-Monitoring-SHA256: <sha256-of-request-bytes>
```

Package contents:

- `schema/monitoring.v1.schema.json`: copied JSON Schema for the wire message.
- `contract/ALGOMATRIC_MONITORING_CONTRACT.md`: copied contract text.
- `fixtures/messages/`: valid and invalid request bodies.
- `fixtures/acks/`: valid and invalid ACK bodies for sender-side tests.
- `cases/http_cases.json`: receiver acceptance cases and expected behavior.
- `receiver_acceptance_test.py`: standalone HTTP runner for a staging receiver.

Run a local manifest check without contacting a receiver:

```bash
python receiver_acceptance_test.py --dry-run
```

Run against a non-production receiver:

```bash
python receiver_acceptance_test.py --endpoint https://staging.example.invalid/api/monitoring/v1/messages --token "$UPLOAD_TOKEN"
```

Expected compatibility means the receiver authenticates, validates schema and
request SHA-256, checks `message_id`, stores idempotency and sequence state by
`(source_id, source_instance)`, returns a valid `monitoring.ack.v1` ACK for
accepted or duplicate messages, rejects gaps/conflicts/oversize/malformed input,
and preserves UNKNOWN, STALE, INCOMPLETE, UNTRUSTED, SYNTHETIC_CLOCK,
HISTORICAL/offline fixture and salvaged classifications exactly.
