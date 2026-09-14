# monitoring.v1 — TLS and transport validation

Companion to `STAGING_VALIDATION.md`.

## 1. Staging TLS setup

A staging-only certificate authority, generated per session into the session
scratchpad. **No production certificate was used, requested or touched.**

| Certificate | Issuer | Hostname | Validity |
|---|---|---|---|
| `server-valid` | Algomatric Staging CA | `localhost` (+ `127.0.0.1`) | current |
| `server-expired` | Algomatric Staging CA | `localhost` | **expired** 2026-08-12 |
| `server-mismatch` | Algomatric Staging CA | `other.staging.invalid` | current |
| `server-untrusted` | Untrusted Issuer (test only) | `localhost` | current |

Four separate receivers were run, one per certificate, so each failure mode
could be observed as its own condition rather than inferred from one.

## 2. Results

Client: Python's `urllib` with the standard `ssl` module — the same client the
producer's acceptance harness uses, so these results describe the real caller.

| # | Condition | Observed |
|---|---|---|
| D1 | Valid certificate, correct hostname, staging CA trusted | **CONNECTED, HTTP 200** |
| D2 | Expired certificate | REFUSED — `certificate has expired` |
| D3 | Hostname mismatch | REFUSED — `Hostname mismatch` |
| D4 | Untrusted issuer | REFUSED — `unable to get local issuer certificate` |
| — | Valid staging certificate against the **system** trust store | REFUSED — `unable to get local issuer certificate` |

That last row is the isolation check: the staging CA is not installed in the
host trust store, so the staging certificate is only accepted by a client that
has been told to trust it explicitly. A staging certificate cannot be mistaken
for a publicly trusted one.

**TLS failure is never a successful delivery.** In every refused case the
connection was terminated during the handshake; no request body was sent and no
message reached the receiver.

## 3. The producer harness over HTTPS

The producer's `receiver_acceptance_test.py` was run **unmodified** against the
staging HTTPS receiver. Verified unmodified by `git status` on the vendored
package, both before and after.

The harness's own trust store was pointed at the staging CA through the standard
`SSL_CERT_FILE` environment variable rather than by editing the harness. That
distinction matters: the file the producer shipped is the file that ran.

    all 11 cases PASS

    duplicate_delivery_100
    identity_conflict_same_id_changed_body
    invalid_request_digest_header
    invalid_token
    malformed_and_oversized_rejection
    new_source_instance_sequence_starts_at_1
    out_of_order_1_3_2
    out_of_order_5_4_6_after_1_2_3
    sequence_gap
    unknown_stale_incomplete_synthetic_salvaged_preserved
    valid_four_message_sequence

Re-run and still passing after every change made in this phase.

## 4. HTTP, redirects and downgrade

### 4.1 The receiver does not terminate TLS in production

TLS terminates at the edge (`deploy/nginx/edge-tls.conf.example`), which then
proxies to the application over plain HTTP on loopback. The application
therefore serves HTTP by design; HTTPS enforcement is the edge's job, and the
example config does redirect port 80 to HTTPS and sets HSTS.

For this phase the receiver terminated TLS directly, which is what made the
certificate matrix above testable at all.

### 4.2 A deployment invariant worth writing down

`POST /api/monitoring/v1/messages/` — with a trailing slash — is answered with a
307 redirect to the canonical path. Measured behaviour behind a TLS-terminating
proxy:

| Request | `Location` |
|---|---|
| Without `X-Forwarded-Proto` | `http://…` — **a downgrade** |
| With `X-Forwarded-Proto: https` (what nginx sends) | `https://…` — correct |

uvicorn trusts forwarded headers from loopback by default and the example nginx
config sets `X-Forwarded-Proto`, so the deployed configuration is correct. But
the correctness depends on that header: **if the edge ever stops sending
`X-Forwarded-Proto`, a trailing-slash POST would hand the producer a plaintext
URL to follow, and the message body would be re-sent unencrypted.**

Not a defect in the current configuration, and not exploitable as deployed. It
is an invariant that has to survive future edge changes, so it is recorded here
rather than left implicit. The producer's canonical endpoint has no trailing
slash, so the redirect is not on the normal path.

### 4.3 The receiver follows no redirects

The receiver makes no outbound HTTP calls at all — verified by search across the
monitoring modules. There is no client in it to follow an insecure redirect
with.

## 5. Transport failure semantics

The producer's behaviour for each outcome is **specified in the canonical
contract**, not inferred. From `ALGOMATRIC_MONITORING_CONTRACT.md`:

| Outcome | LLS behaviour, per the contract |
|---|---|
| DNS/TCP/TLS failure, reset, timeout, invalid ACK | retain pending message and **retry with stable identity** |
| 408, 425, 429, 5xx | retry with bounded exponential backoff |
| Other 4xx, including 401/403/409/413 | retain blocked delivery, expose the error, **retry slowly after 900 seconds** |
| Success with validated identity | acknowledge and proceed to the next sequence |
| Exhausted attempts or capacity | mark degraded, retain evidence, require an operator. **Never backpressure Core.** |

What the receiver emits, and what each means to the producer:

| Status | Emitted for | Producer response |
|---|---|---|
| 200 | accepted or duplicate | drop from the queue |
| 400 | malformed, bad digest, forged identity | blocked; retry after 900 s |
| 401 | not authenticated | blocked; retry after 900 s |
| 403 | authenticated, wrong source | blocked; retry after 900 s |
| 409 | sequence refused | blocked; retry after 900 s |
| 413 | too large | blocked; retry after 900 s |
| 422 | unsupported version or schema-invalid | blocked; retry after 900 s |
| 503 | storage unavailable or refused the write | bounded exponential backoff |

### Why the oversized path drains before answering

This is the decision that the contract table above justifies. A body over the
transport ceiling could be refused by closing the connection immediately — which
is cheaper — but the client would see a **connection reset**, and the contract
routes a reset to *"retry with stable identity"*, the fast path. A 413 routes to
*"retry slowly after 900 seconds"*.

So closing early would make the producer resend an impossible message roughly
90x more often than answering properly does. The receiver therefore drains the
upload without buffering it and returns a real 413. The memory — which was the
actual vulnerability — stays bounded either way; only bandwidth is spent.

### 503 is deliberately wide

Staging measurement found a read-only database surfacing as `InternalError` and
a revoked grant as `ProgrammingError`, neither of which is an `OperationalError`.
Both previously escaped as an unhandled **500**. Both are retryable under the
contract's 5xx rule, so no message was ever at risk — but 500 says "something
broke" where 503 says "storage did not take this, try again", which is the
honest answer and the one the producer is designed around. Every database error
that prevents the write now maps to 503.

Not tested: 408, 425, 429, 502, 504. The application emits none of them; they
are edge and proxy behaviours, and reproducing them would be testing nginx
rather than this contract. Recorded as NOT TESTED.
