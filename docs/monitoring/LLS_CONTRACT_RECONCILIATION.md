# monitoring.v1 contract reconciliation

**Date:** 2026-09-11
**Decision applied:** LLS `monitoring.v1` is the canonical wire contract. Algomatric is the receiver.

---

## Gate result

| Gate | Result |
|---|---|
| LLS fixtures accepted | **19 / 19** |
| Canonical JSON compatible | **PASS** |
| Hash scope compatible | **PASS** |
| Sequence semantics compatible | **FAIL — not implemented** |
| Freshness semantics compatible | **FAIL — not implemented** |
| Environment semantics compatible | **FAIL — not implemented** |
| Runtime semantics compatible | **FAIL — not implemented** |
| No invented values | **PASS** |

**Not all PASS. Do not proceed to PostgreSQL / E2E staging.**

The four FAILs are all the same fact stated four ways: the *contract layer* now
speaks monitoring.v1, and the *receiver pipeline* behind it does not yet. Each
is "not implemented", none is "implemented incorrectly", and nothing currently
misrepresents LLS data because nothing is currently accepted — the superseded
ingress fails closed.

## What changed

### Canonical contract installed

| | |
|---|---|
| [`schemas/monitoring-v1/`](../../schemas/monitoring-v1) | `monitoring.v1.schema.json` + `ALGOMATRIC_MONITORING_CONTRACT.md`, copied **verbatim** from the LLS handoff package |
| Drift guard | two tests assert both files are byte-identical to their copies in the vendored package |
| Provenance | [`PROVENANCE.md`](../../schemas/monitoring-v1/PROVENANCE.md) records source path, hashes, resync procedure |

`schemas/monitoring-export/v1/` is gone from `schemas/`. It is retained as
history at [`superseded/monitoring-export-v1-proposal/`](superseded/monitoring-export-v1-proposal)
with a README explaining what it was and why it was retired. A test asserts
`schemas/` now contains exactly one contract directory, so a second one cannot
reappear unnoticed.

### Contract layer rewritten

[`ops/backend/app/monitoring/contract.py`](../../ops/backend/app/monitoring/contract.py):

- loads the canonical schema and refuses to start if its `schema_version` const
  is not `monitoring.v1`
- `classify_version` is an **exact match**, not a range. The contract states the
  version identifies field *meaning*, so there is no forward-compatible reading
  of an unknown version — a `monitoring.v2` message could reuse field names to
  mean different things. Unsupported ⇒ quarantine, never guess.
- `message_identity()` computes `mon1/` + SHA-256 of the canonical JSON with
  `message_id` removed, so identity is **verified rather than trusted**
- `request_digest()` hashes the **whole request body** (see below)
- `parse_message()` rejects duplicate keys and non-finite numbers **at parse
  time** — `json.loads` would otherwise keep the last duplicate and silently
  produce `Infinity`
- `check_limits()` enforces the normative limits JSON Schema cannot express:
  1 MiB request, 100 array items, depth 24, 30,000 nodes, 4,096 chars per string
- `parse_sequence()` returns an int for ordering **only**; the original string is
  what gets stored and echoed, because the ACK carries `source_sequence` as a
  string and a receiver that re-rendered it would fail the sender's identity check

### Hash scope corrected

The superseded implementation hashed a nested `observation` sub-object. That was
wrong and has not been kept.

| | |
|---|---|
| Now | SHA-256 over the whole request body, per the contract |
| Verified | matches the producer manifest `sha256` for **all 19** fixtures |
| Regression guard | `test_digest_is_not_computed_over_a_sub_object` fails if sub-object hashing returns |

### Canonical JSON preserved

The existing algorithm was already correct and is unchanged: UTF-8, sorted keys,
compact separators, non-ASCII unescaped. Now proven against the real producer:

- `canonical_json(parse(raw)) == raw` for **all 19** fixtures, byte for byte
- every `message_id` recomputes to exactly the value the producer assigned —
  which is only possible if our canonicalisation matches theirs exactly

## The gate in detail

### LLS fixtures accepted — 19 / 19

`ops/backend/tests/test_monitoring_v1_contract.py`, 42 tests, all passing.

Each producer-valid fixture is parsed under the contract's parsing rules,
checked against the normative limits, version-classified, schema-validated, and
its content address recomputed. Before: 0/19. Now: 19/19.

### Negative fixtures retain their behaviour

| Fixture | Outcome | Reason |
|---|---|---|
| `malformed_duplicate_keys.json` | rejected | duplicate key detected at parse |
| `bad_schema_version.json` | quarantined | unsupported version — quarantined, not rejected |
| `invalid_message_id.json` | rejected | content address does not match the body |
| `oversized_string.json` | rejected | exceeds 4,096 characters |
| `excessive_nesting.json` | rejected | deeper than 24 levels |
| `conflict_same_id_changed_payload.json` | rejected | identity mismatch |

A blanket test asserts **no** fixture the producer marked invalid is ever
accepted, so a new negative fixture in a future package is covered automatically.

The conflict case is worth noting: under monitoring.v1 a reused id with changed
bytes is caught at the **contract layer** by the content address, before it can
reach storage at all. The superseded design could only detect this after writing
evidence and comparing hashes. Adopting the LLS identity scheme made this
strictly better.

### No invented values — PASS

- `test_no_stale_after_exists_anywhere_in_the_contract` asserts the string
  `stale_after` appears nowhere in the canonical schema
- nothing synthesises a horizon, because nothing currently ingests
- `test_qualified_values_carry_status_and_may_carry_an_explicit_null` asserts
  LLS's `{"value": null, "status": "UNKNOWN", "reason": ...}` is preserved
  including the explicit null — the superseded proposal required the value key to
  be *absent*, and stripping it would have been a silent edit of producer data

## The four FAILs — what each needs

These are pipeline work, not contract work.

### Sequence semantics — FAIL

| | |
|---|---|
| Contract requires | expect 1 first, then the next sequence; **reject gap or unknown older sequence with 409**, retaining the last accepted state; a previously accepted duplicate may be acknowledged again after later sequences |
| Receiver has | the opposite by design — accept everything, record the gap, surface it |
| Needed | replace the accept-and-record policy with the contract's 409-and-retain policy at the protocol boundary |

This was the most consequential behavioural conflict in the compatibility report
and it is now settled by the decision: LLS's policy wins. The receiver's
gap-visibility machinery is still useful *below* the protocol boundary, but it
must no longer decide the HTTP outcome.

### Freshness semantics — FAIL

| | |
|---|---|
| Contract requires | freshness is an **asserted state** (`freshness.source: "STALE"`), derived from source validity and trust, never from arrival time |
| Receiver has | horizon logic in `app/monitoring/freshness.py`, `stale_after` columns on two tables, and a client-side timer in `frontend/src/lib/monitoring.ts` |
| Needed | remove the horizon model and display LLS's asserted state |

The horizon code is currently **unreachable** — nothing ingests, so nothing
evaluates it — but it has not been replaced and must not be wired to LLS data.

### Environment semantics — FAIL

| | |
|---|---|
| Contract requires | `offline_fixture`, `replay`, `offline_live_shaped`, `live_market_paper`, `broker_sandbox`, `live_trading`, `unknown` — **market reality** |
| Receiver has | `production` / `staging` / `development` / `test` — **deployment tier**, used as a storage and query boundary |
| Needed | store LLS's value unmodified, and decide separately how deployment-tier isolation is expressed, since the producer does not send it |

Per rule 10, the missing deployment-tier information becomes UNKNOWN rather than
being inferred from the market-reality value. Mapping `live_trading` → production
would be exactly the kind of invention this reconciliation removed.

### Runtime semantics — FAIL

| | |
|---|---|
| Contract requires | an **array of capture identifiers**, e.g. `["historical-final/2503001"]` |
| Receiver has | an enum `LIVE/SIMULATED/HISTORICAL/REPLAY/UNKNOWN` driving the "never show simulated as live" UI rule |
| Needed | store the array verbatim; derive the display treatment from `environment` and `coverage.capture_status`, which is where LLS actually expresses it |

## Current receiver state

The superseded ingress **fails closed**. `POST /api/v1/monitoring/export` now
returns `503` with an explicit reason rather than 500 or, far worse, `200`: a
publisher that received an acknowledgement there would delete data from its
durable queue that this receiver never stored.

The canonical ingress `POST /api/monitoring/v1/messages` is **not yet
implemented**.

`ops/backend/tests/test_monitoring_receiver.py` (61 tests) is **skipped**, not
deleted. It encodes the receiver capabilities that survive the contract change —
immutable evidence, quarantine distinct from dead-lettering, conflict retention,
projection rebuild, environment isolation, and the structural no-trading-controls
guard. Each has to be re-expressed against monitoring.v1 fixtures during the
pipeline migration, and that file is the checklist for it. Deleting it would lose
the checklist; leaving it running would report 61 failures that say only "the
contract changed", which is already known.

## Next step

Pipeline migration, in this order:

1. Evidence model shaped to the LLS envelope — `message_type`, `source_sequence`
   as a string, `source_as_of` object, `coverage`/`freshness`/`trust` stored
   verbatim, whole-message digest, no `stale_after`
2. Ingress at `POST /api/monitoring/v1/messages`, single message, with the
   contract's 409 sequence policy and the exact `monitoring.ack.v1` body
3. Projections keyed by `message_type` and `capture_ref`
4. API and UI reading the asserted freshness state
5. Re-express the 61 skipped capability tests against LLS fixtures

Only when all eight gates read PASS does PostgreSQL / E2E staging begin.

## Rules honoured

| Rule | How |
|---|---|
| LLS structure/fields/semantics canonical | schema copied verbatim; drift guarded by hash tests |
| LLS knowledge states preserved | explicit null preserved; state vocabulary untouched |
| Do not synthesize `stale_after` | asserted by test; horizon code isolated and unused |
| Do not convert STALE into a local horizon | horizon model not wired to LLS data |
| Preserve `environment` semantics | not reinterpreted; mapping explicitly refused |
| Preserve `runtime` semantics | array not coerced to an enum |
| Follow LLS sequence semantics | acknowledged as required; **not yet implemented** |
| Preserve source and message identity exactly | identity recomputed and verified for all 19 |
| Do not discard information | nothing ingested yet; evidence model will store the envelope verbatim |
| Normalize only after evidence preserved | no normalisation exists in the contract layer |
| UI must not manufacture knowledge | UI not yet wired to monitoring.v1 |
| Do not modify the LLS producer or contract | LLS repo untouched; `docs/black_box/` shows no modification |
| Do not build an adapter that invents semantics | no adapter was built |
