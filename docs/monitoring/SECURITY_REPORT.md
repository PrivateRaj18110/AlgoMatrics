# Security report — monitoring.v1 receiver

## 1. Credential model

Three identities, deliberately unable to substitute for one another:

| Identity | Configured by | Can |
|---|---|---|
| **Publisher** | `MONITORING_SOURCE_TOKENS="<source_id>:<token>,…"` | POST observations for **one** `source_id`. Nothing else. |
| **Dashboard viewer** | `RAJ_DASHBOARD_TOKEN` / `OPS_JWT_PUBLIC_KEY` | read projections, evidence, sources, conflicts |
| **Monitoring administrator** | `MONITORING_ADMIN_TOKEN` | additionally read quarantined material |

Separate digest indexes, so the boundaries cannot merge by accident:

- A **Raj agent** token does not authenticate a monitoring upload — `test_agent_credential_does_not_authorize_monitoring_upload`.
- A **publisher** token does not grant administrative access — `test_publisher_credential_grants_no_administrative_access`.
- A publisher token scoped to source A cannot publish as source B — `test_credential_cannot_publish_for_another_source` (403).

The upload identity grants no read access at all. A publisher cannot read back what the receiver rejected from other publishers.

## 2. Fail closed

An unconfigured server rejects every upload rather than accepting every upload. `monitoring_token_index` empty ⇒ 401 for all requests.

Adding monitoring credentials was **not** made a production startup requirement, deliberately: an existing deployment that does not use monitoring.v1 yet should keep starting, and the route is safe when unconfigured because it rejects everything.

Tokens are stored only as SHA-256 digests. Lookup hashes the presented token and compares fixed-width digests, so comparison time does not vary with how much of a real credential was guessed. Every rejection returns the same opaque message regardless of cause.

## 3. Scope enforcement is layered

`source_id` is checked in three places, because they fail differently:

1. **Batch wrapper** vs credential → `403`, request refused.
2. **Each envelope** vs credential → per-message `REJECTED`. A batch cannot smuggle one foreign envelope past a valid wrapper — `test_a_valid_wrapper_cannot_smuggle_a_foreign_envelope` asserts the foreign message is rejected and reaches no evidence row.
3. **Environment** (optional, `MONITORING_SOURCE_ENVIRONMENTS`) → per-message `REJECTED`. A staging publisher can be barred from writing production rows.

Environment isolation is also a **storage boundary**, not a display filter: `/state?environment=production` never loads a staging row, so a UI bug cannot leak one.

## 4. Audit

`monitoring_audit` records ingestion outcomes, batch-level rejections, scope violations and per-batch counts, with `source_id`, `request_id` and `remote_addr`.

Never recorded: the token, the `Authorization` header, or any secret. The audit row carries the outcome and the identity the credential mapped to — not the credential.

Forensic rows are committed **before** a 4xx is raised, so a refused upload still leaves a record. Rolling them back would make rejected traffic invisible.

## 5. Input validation

Every message is validated against the published JSON Schema before it can reach a projection. There is no `data: dict` escape hatch on the route. Unknown fields at the receiver's own version are quarantined, not ignored.

Size limits (contract §2):

| Limit | Value | Enforced |
|---|---|---|
| Batch items | 1000 | before schema validation, so it reports 413 not 400 |
| Decompressed body | 8 MiB | **after** gzip decompression |
| Single envelope | 256 KiB | per message, canonicalised |

`test_compression_cannot_smuggle_an_oversized_body` sends a payload that is under 2 KiB compressed and over the limit decompressed, and asserts 413. Compression cannot bypass the size limit.

## 6. Known exposure — gzip decompression is unbounded

**This is a real finding and it is not fixed.**

`GzipRequestMiddleware` (shared with the agent path) decompresses the entire request body into memory *before* any size limit is applied. The monitoring route's 8 MiB check runs after that. A gzip bomb — a few hundred KB expanding to gigabytes — would be fully decompressed before it was rejected.

Mitigations in place: the route requires authentication, so an anonymous attacker cannot reach it, and rate limiting applies at nginx.

Why it was not fixed here: the middleware is shared with the `raj_monitor` agent path, which handles EOD chunk uploads up to 25 MiB. Adding a hard cap risks breaking that path, and verifying it was out of scope for this work.

**Recommended fix:** stream-decompress with a byte ceiling (`zlib.decompressobj().decompress(chunk, max_length)`), with the ceiling configurable per route and defaulting above the agent's largest legitimate upload.

## 7. No trading capability

Structurally, not by permission:

- One write operation exists across both monitoring surfaces (`POST /export`) and it writes observations.
- `test_monitoring_routes_expose_no_control_actions` asserts this against the published OpenAPI surface and fails if any path contains `cancel`, `modify`, `resubmit`, `flatten`, `restart`, `halt`, `execute`, `trade`, `place` or `shutdown`.
- `test_contract_exposes_no_trading_actions` asserts the same for every field name in the published schemas, so a control cannot enter through the contract either.
- `ops/backend/tests/test_execution_isolation.py` (pre-existing) already fails the build if the ops backend gains a dependency on broker login, order placement, strategy execution, signal routing or risk control.

There is no reverse path to LLS: no filesystem, database, process or API access, in either direction beyond the inbound HTTPS ingress.

## 8. Not verified

| | |
|---|---|
| **NOT TESTED** | credential rotation and revocation under live traffic — the mechanism is environment-variable based and restart-scoped |
| **NOT TESTED** | rate limiting on the monitoring route specifically (nginx-level, configured for `/ops/api/`, not separately exercised) |
| **NOT DONE** | no dependency vulnerability scan was run as part of this work |
| **NOT DONE** | no penetration testing, no fuzzing of the ingress |
| **REQUIRES PRODUCTION ACCESS** | TLS configuration, certificate validity, firewall rules, secret storage |
