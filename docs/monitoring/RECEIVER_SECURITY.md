# monitoring.v1 receiver — security

## 1. Credential model

Three identities that cannot substitute for one another:

| Identity | Configured by | Can |
|---|---|---|
| **Publisher** | `MONITORING_SOURCE_TOKENS="<source_id>:<token>,…"` | POST monitoring.v1 messages for **one** `source_id`. Nothing else. |
| **Dashboard viewer** | `RAJ_DASHBOARD_TOKEN` / `OPS_JWT_PUBLIC_KEY` | read projections, evidence, sources |
| **Administrator** | `MONITORING_ADMIN_TOKEN` | additionally read quarantined material |

Separate digest indexes, tested:

- a **Raj agent** token does not authenticate a monitoring upload — `test_agent_credential_does_not_authorize_monitoring_upload`
- a **publisher** token does not grant administrative access — `test_publisher_credential_grants_no_administrative_access`
- a publisher scoped to source A cannot publish as source B — `test_credential_cannot_publish_for_another_source` (403)

Tokens are stored only as SHA-256 digests. Lookup compares fixed-width digests, so comparison time does not vary with how much of a real credential was guessed. Every rejection returns the same opaque message.

## 2. Authentication precedes everything

The route reads the request body **after** the credential dependency resolves. A body is never parsed on behalf of an unauthenticated caller, and `test_authentication_happens_before_persistence` asserts an unauthorised body leaves no evidence and no projection.

## 3. Source spoofing

Checked twice, because they fail differently:

1. the credential establishes the permitted `source_id`
2. the **message's own** `source_id` is compared against it → 403 `source_not_authorized`

A valid credential cannot publish a message attributed to another source.

## 4. Identity forgery

`message_id` is a content address. The receiver recomputes `mon1/sha256(canonical JSON without message_id)` and compares. A forged or reused identity with altered bytes cannot match, and is refused before it reaches storage — `test_forged_message_id_is_refused`, `test_reused_identity_with_changed_body_is_refused`.

The optional `X-Monitoring-SHA256` header is verified against the whole request body when present — `test_declared_request_digest_is_verified`.

## 5. Hostile input — exercised, not assumed

`test_hostile_bodies_are_refused_without_damage` posts each of these and asserts a 4xx and an intact database:

```
{                                 truncated JSON
(empty body)                      no content
[]                                wrong root type
{"schema_version": "..."          unterminated
\xff\xfe …                        invalid UTF-8
{"a": Infinity}                   non-finite
{"a": NaN}                        non-finite
{"a": 1, "a": 2}                  duplicate keys
{"source_id": "x'; DROP TABLE …"} SQL injection attempt
{"source_id": "<script>…"}        script injection attempt
```

Duplicate keys and non-finite numbers are rejected **at parse time** rather than normalised away — `json.loads` would otherwise silently keep the last duplicate and happily produce `Infinity`.

`test_sql_injection_in_a_valid_message_is_not_executed` goes further: it builds a *schema-valid* message carrying a SQL payload in `source_instance`, recomputes a genuine content address for it, posts it, and asserts the table still exists. All SQL is parameterised; this proves it rather than claiming it.

## 6. Structural limits

Enforced from the contract's normative values, which JSON Schema cannot express:

| Limit | Value | Response |
|---|---|---|
| Request body | 1 MiB | 413 |
| Nesting depth | 24 | 413 |
| Total nodes | 30,000 | 413 |
| Array elements | 100 | 413 |
| String length | 4,096 | 413 |

`oversized_string.json` and `excessive_nesting.json` from the producer's package are both refused with 413.

## 7. Quarantine

Refused-as-uninterpretable material is preserved with the original request bytes, is **administrator-only**, and never enters a projection — `test_quarantined_material_never_becomes_a_projection`, `test_quarantine_is_not_visible_to_dashboard_viewers`.

A **sequence refusal is not quarantined**. A well-formed message refused for ordering is not defective — it arrived early and will be resent in order. Quarantining it would imply the producer sent something broken.

## 8. Audit and credential hygiene

`monitoring_audit` records ingestion outcomes, refusals and scope violations with `source_id`, `request_id` and `remote_addr`. Never the token, never the `Authorization` header.

`test_credentials_never_appear_in_the_audit_log` posts with both a valid and an invalid credential and asserts neither string appears in any audit row.

Forensic rows are committed **before** a 4xx is raised, so a refused upload still leaves a record.

## 9. No trading capability

Structural, not by permission:

- exactly one write operation exists across the monitoring surface, and it writes observations
- `test_monitoring_routes_expose_no_control_actions` asserts this against the published OpenAPI surface, failing on any path containing `cancel`, `modify`, `resubmit`, `flatten`, `restart`, `halt`, `execute`, `trade`, `place`, `shutdown`, `enable`, `disable`
- `test_execution_isolation.py` (pre-existing) fails the build if the ops backend gains a dependency on broker login, order placement, strategy execution, signal routing or risk control

No reverse path to LLS exists in any direction beyond the inbound HTTPS ingress.

## 10. Known exposure — gzip decompression is unbounded

**Not fixed. Stated plainly.**

`GzipRequestMiddleware`, shared with the `raj_monitor` agent path, decompresses the entire request body into memory before any size limit applies. The monitoring route's 1 MiB check runs after that, so a gzip bomb would be fully expanded before rejection.

Mitigations in place: the route requires authentication, and nginx rate-limits `/ops/api/`.

Why it was not fixed here: the middleware is shared with the agent's EOD chunk path, which legitimately carries up to 25 MiB. A hard cap risks breaking that path, and verifying it is out of scope for this work. **Recommended fix:** stream-decompress with a per-route byte ceiling (`zlib.decompressobj().decompress(chunk, max_length)`), defaulting above the agent's largest legitimate upload.

Note that for monitoring.v1 specifically the *effective* limit is still enforced — a decompressed body over 1 MiB is refused with 413. The exposure is memory during decompression, not limit bypass.

## 11. Not verified

| | |
|---|---|
| **NOT TESTED** | TLS: certificate validation, hostname validation, expired/invalid certificate rejection, redirect downgrade. Staging ran over plain HTTP on loopback. |
| **NOT TESTED** | credential rotation and revocation under live traffic (environment-variable based, restart-scoped) |
| **NOT TESTED** | rate limiting on the monitoring route specifically |
| **NOT DONE** | dependency vulnerability scan, fuzzing, penetration testing |
| **NOT RESOLVED** | quarantine retention is unbounded — see `STAGING_READINESS.md` |
| **REQUIRES PRODUCTION ACCESS** | firewall rules, secret storage, certificate provisioning |
