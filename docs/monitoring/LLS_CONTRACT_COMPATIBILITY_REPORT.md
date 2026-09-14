# LLS ↔ Algomatric contract compatibility report

**Date:** 2026-09-11
**Verdict:** the two contracts are **not compatible**. This is not a field-naming delta — they are two independently designed contracts for the same problem.

**Nothing was changed on either side.** Per the stop rule, this report exists so the mismatch can be resolved deliberately rather than patched.

---

## 0. Provenance

| | |
|---|---|
| LLS package | `docs/black_box/implementation/algomatric_contract_fixture_package/` in the LLS repo |
| Vendored to | [`tests/fixtures/lls-monitoring-v1-handoff/`](../../tests/fixtures/lls-monitoring-v1-handoff) (verbatim copy, read-only use) |
| Package self-check | `python receiver_acceptance_test.py --dry-run` → `{"status":"dry-run-ok","messages":22,"cases":11}` |
| Package independence | confirmed — `receiver_acceptance_test.py` imports only stdlib; no LLS code, DB, or filesystem dependency |
| LLS repo modified | **no** |
| Algomatric schemas modified | **no** |

The LLS repository was read to locate the package and copied from. Nothing in it was written to.

## 1. The measured result

Every LLS fixture marked `producer_valid: true` was validated against
`schemas/monitoring-export/v1/envelope.schema.json`:

```
Accepted by the Algomatric receiver schema: 0/19
```

All 19 fail at the first field checked (`message_id`), and would fail on ten more
after that. Live HTTP probes against a running receiver:

| Request | Result |
|---|---|
| `POST /api/monitoring/v1/messages` (the path LLS expects) | **404** — route does not exist |
| `POST /api/v1/monitoring/export` with an LLS message body verbatim | **400** — `'messages' is a required property` |
| `receiver_acceptance_test.py --endpoint …/api/v1/monitoring/export` | **refused to start** — *"endpoint must end in /api/monitoring/v1/messages"* |

The LLS acceptance harness cannot be pointed at the current receiver without
modifying the harness, which is the authoritative artifact and was left alone.

## 2. Transport

| Field | LLS definition | Algomatric definition | Difference | Compatibility impact | Proposed owner |
|---|---|---|---|---|---|
| Endpoint | `POST /api/monitoring/v1/messages` | `POST /api/v1/monitoring/export` | different path | total — 404 | **Algomatric** (cheap, no semantic content) |
| Body | one message per request | batch wrapper `{schema_version, source_id, source_instance, sent_at, messages[]}` | single vs batch | total — 400 | **Joint decision** |
| Idempotency | `Idempotency-Key: <message_id>` header | `message_id` inside the body | transport vs body | receiver ignores the header | **Algomatric** (can accept both) |
| Integrity | `X-Monitoring-SHA256` header, sha256 over **request bytes** | `integrity.digest` in body, sha256 over the **`observation` sub-object** | different scope | cannot verify either way | **Algomatric** (see §5) |
| ACK | `monitoring.ack.v1`: flat `{message_id, schema_version, sha256, source_sequence, status}` per message | batch ack `{schema_version, received_at, counts{}, outcomes[]}` | per-message vs per-batch | publisher cannot parse our ACK | **Joint decision** (follows the batch decision) |
| ACK statuses | `accepted`, `duplicate` | `ACCEPTED`, `DUPLICATE`, `QUARANTINED`, `CONFLICT`, `REJECTED`, `FAILED` | LLS has 2, we have 6 | LLS treats everything else as an HTTP error code | **Joint decision** |

## 3. Envelope fields

| Field | LLS definition | Algomatric definition | Difference | Compatibility impact | Proposed owner |
|---|---|---|---|---|---|
| `schema_version` | const `"monitoring.v1"` | pattern `^1\.\d+$` (e.g. `"1.0"`) | different value space | our version classifier quarantines every LLS message | **Joint decision** |
| `message_id` | `^mon1/[0-9a-f]{64}$` — content-addressed | UUID v4 | format and semantics | rejected; also changes what idempotency *means* (content hash vs opaque id) | **Joint decision** |
| `message_type` | enum of 4: `monitoring.snapshot`, `.events`, `.incidents`, `.forensic_reference` | no such field; discriminator is `observation.kind`, enum of 14 | different decomposition | **structural** — see §4 | **Joint decision** |
| `source_sequence` | **string** `^[1-9][0-9]{0,18}$`, starts at 1 | `sequence`, **integer** ≥ 0 | name + type + origin | rejected on both name and type | **Algomatric** (accept string, coerce) |
| `source_as_of` | **object** `{acquired_at_ns, source_time{qualified}, valid_at}` | `data_as_of`, RFC-3339 **string** | name + type | rejected; our staleness input is absent | **Joint decision** |
| `runtime` | **array of strings**, e.g. `["historical-final/2503001"]` — capture identifiers | **enum** `LIVE/SIMULATED/HISTORICAL/REPLAY/UNKNOWN` | type and meaning | rejected; our "never show simulated as live" rule has no input | **Joint decision — semantic** |
| `environment` | enum of 7: `offline_fixture`, `replay`, `offline_live_shaped`, `live_market_paper`, `broker_sandbox`, `live_trading`, `unknown` | enum of 4: `production`, `staging`, `development`, `test` | different axis entirely — LLS describes *market reality*, we describe *deployment tier* | rejected; our isolation boundary keys on a concept LLS does not send | **Joint decision — semantic** |
| `coverage` | envelope-level object `{status, capture_status, reason}` | inside `observation.qualifiers.coverage` as `{ratio, observed, expected, …}` | location **and** shape (qualitative vs quantitative) | rejected; our coverage UI expects a ratio LLS never sends | **Joint decision — semantic** |
| `freshness` | envelope-level `{derived_at, reason, source}` where `source` ∈ STALE/UNKNOWN/… | inside qualifiers as `{data_as_of, stale_after, state, expected_interval_ms}` | location and model | **critical** — see §6 | **Joint decision — semantic** |
| `trust` | envelope-level `{status, scope, independent_broker}` | inside qualifiers as `{level, basis, confidence}` | location and vocabulary | rejected | **Joint decision** |
| `payload` | typed per `message_type` | `observation.payload` typed per `kind` | different nesting | rejected | **Joint decision** |
| `entity` | **absent** | `{type, id}` — the anchor for revision and conflict | LLS has no entity concept | our revision/conflict model has no input | **Joint decision — semantic** |
| `revision` | **absent** | integer restatement counter | LLS has no restatement concept | see §7 | **Joint decision — semantic** |
| `supersedes`, `correlation`, `capture_id` | absent (`capture_ref` lives in payload) | present | — | unused | Algomatric |

Fields shared by name: `schema_version`, `message_id`, `source_id`, `source_instance`, `generated_at`, `runtime`, `environment`. **Of those six, only `source_id`, `source_instance` and `generated_at` are compatible in both type and meaning.**

## 4. Payload decomposition — the structural difference

LLS sends **four message types**, one of which (`monitoring.snapshot`) carries the entire system state in one message with 18 required sections:

```
capture_ref, definition, system, feed, processing, strategy, risk, execution,
orders, fills, positions, pnl, latency, errors, incidents, reconciliation,
observer, evidence
```

Algomatric expects **fourteen observation kinds**, one subject per message
(`feed_status`, `order_lifecycle`, `position`, …).

These are not translatable by renaming. One LLS snapshot corresponds to *many*
Algomatric observations, and the split would have to be performed by whichever
side takes ownership — which is itself a contract decision, because it
determines who owns the decomposition and therefore who can get it wrong.

LLS additionally carries two concepts with no Algomatric equivalent:

- **`observer`** — the observer's own state, distinct from the Core's
- **`evidence`** — artifact list with `{role, bytes, sha256, coverage}` plus
  `salvage` status per role (`SEALED_VALID`, `UNSEALED_SALVAGEABLE`)

The salvage/evidence model is richer than our `EvidenceRef` and is the part of
the LLS contract most clearly backed by a real producer.

## 5. Canonical JSON — a genuine partial match

**This was the mandatory gate, and the result is unusually good news.**

| | |
|---|---|
| LLS fixture bytes | already `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)` |
| Re-canonicalising with the Algomatric `contract.canonical_json` | **byte-identical** to the original file |
| `sha256(raw bytes)` | `de7846f8…288e` |
| Manifest `sha256` | `de7846f8…288e` — **match** |

**The serialisation algorithm is identical on both sides.** The encoding
question flagged as the top interoperability risk in the previous report is
settled: UTF-8, sorted keys, compact separators, unescaped non-ASCII, on both
sides, verified byte-for-byte against a real producer fixture.

What differs is only the **scope of the hash**:

| | Hashed over |
|---|---|
| LLS | the entire request body bytes |
| Algomatric | the canonical JSON of the `observation` sub-object |

LLS messages have no `observation` key, so the Algomatric digest is not
computable over them. This is the **cheapest mismatch in this document to
resolve** and the owner is clearly Algomatric: hashing the whole message is
strictly simpler and strictly stronger than hashing a sub-object.

## 6. Freshness — the semantic difference that matters most

| | LLS | Algomatric |
|---|---|---|
| Model | the **source asserts** its own state: `freshness.source: "STALE"` | the source supplies a **validity horizon**: `freshness.stale_after` |
| Receiver's job | display the asserted state | compare the horizon against the clock, continuously |
| `stale_after` | **does not exist** | required for any STALE verdict |

Both are defensible, and both honour "the dashboard must not invent a staleness
policy". They are not combinable by default:

- Under the LLS model, our client-side "goes STALE by itself at the horizon"
  behaviour has **no input at all** — `evaluateFreshness` would return `UNKNOWN`
  for every LLS message, forever, because no horizon is ever supplied.
- A dashboard fed LLS messages would therefore show *freshness unknown* rather
  than *stale*, which is honest but strictly less useful than what LLS can
  already tell us.

The LLS fixture `unknown_stale_incomplete_synthetic_salvaged.json` carries
`freshness.source: "STALE"` with reason `fixture_preserves_stale_without_live_upgrade`
— the producer is explicitly testing that a receiver does not upgrade STALE to
live. Our receiver would preserve that correctly *if* it read the field.

**Proposed owner: joint, and this one deserves a real conversation** rather than
a mechanical mapping. The two models answer different questions — "is it stale
now?" versus "was it stale when observed?" — and a monitoring dashboard arguably
needs both.

## 7. Behavioural differences

From `cases/http_cases.json` — these are behaviours, not field names, and they
conflict directly with implemented and tested Algomatric behaviour.

| Case | LLS expects | Algomatric implements | Conflict |
|---|---|---|---|
| Sequence gap | **HTTP 409** — reject the message | **accept**, record the gap, surface it | **direct** — we deliberately never reject the message that reveals a gap, because that destroys the evidence of loss. LLS deliberately refuses to accept out-of-order state. |
| Out of order (1, 3, 2) | 3 → **409**; then 2 → accepted; strict in-order gating | all accepted; ordering resolved by revision/sequence at projection time | **direct** |
| Old sequence, changed body | **409** | accepted and stored as evidence; projection unmoved | **direct** |
| Duplicate ×100 | first `accepted`, then `duplicate` ×100, one logical row | identical behaviour | **compatible** |
| New `source_instance` starts at 1 | accepted | accepted, new sequence row | **compatible** |
| Conflict (same id, changed payload) | 409 | `CONFLICT`, both retained, projection unmoved | different mechanism, same intent |

The gap/ordering conflict is the most consequential: LLS's producer is built to
**retry until accepted in order**, while our receiver is built to **accept
everything and make loss visible**. Each is coherent on its own. Together they
produce a publisher that retries forever against a receiver that already
accepted the message.

## 8. Where the two agree

Worth stating, because it is substantial and it is what makes reconciliation
realistic rather than a rewrite:

- Qualified values with an explicit knowledge state, carrying `reason`
- The vocabulary itself: `UNKNOWN`, `STALE`, `UNTRUSTED`, `INCOMPLETE`, `SYNTHETIC_CLOCK`
- Unknown must never become zero, and stale must never become live
- Evidence is content-addressed with sha256 and coverage qualifiers
- Idempotency on a stable message identity, duplicates producing one logical row
- Sequence state scoped to `(source_id, source_instance)`; restart starts a new sequence
- Canonical JSON encoding — **verified byte-identical** (§5)
- No trading controls anywhere in the contract

One notable shape difference inside the shared idea:

| | |
|---|---|
| LLS | `{"status": "UNKNOWN", "value": null, "reason": "not_available"}` |
| Algomatric | `{"state": "UNKNOWN", "reason": "not_available"}` — `value` **must be absent** |

Our schema rejects LLS's form because `value: null` is present. Note this is a
*stricter* reading of the same principle: we made "UNKNOWN carries no value"
unrepresentable, LLS represents it as an explicit null. Both prevent the zero
substitution; ours prevents it at the schema level.

## 9. Resolution options — for decision, not for me to pick

**Option A — Algomatric adopts monitoring.v1.**
The LLS contract is backed by a real producer, real captures, 109 passing
producer-side tests and a generated fixture package. Ours has no producer.
Cost: the receiver's envelope handling, projections keying, freshness model and
UI wiring are rewritten; the storage model, immutability, quarantine, audit and
qualified-value rendering largely survive. The 14-kind decomposition is replaced
by 4 message types.

**Option B — LLS adopts monitoring-export/v1.**
Cost falls entirely on the producer, which already ships and is tested. Loses
LLS's salvage/observer/evidence richness unless ported. Hard to justify on
evidence.

**Option C — a translation layer on the Algomatric side.**
A monitoring.v1 → monitoring-export/v1 adapter at ingress. Preserves both sides'
existing work. **This is where I would want the most scrutiny before proceeding:**
the adapter would have to decompose one snapshot into many observations and
derive a `stale_after` that LLS never sends. Deriving a horizon is exactly the
invented staleness policy both contracts forbid. An adapter that is honest about
this would have to leave freshness UNKNOWN, which loses information LLS is
willing to give us.

**Option D — converge on a v2** informed by both, with LLS's evidence/salvage
model and the receiver's qualified-value strictness.

I am not choosing. Options A and D look strongest on the evidence; C is the most
tempting and the most likely to quietly reintroduce fabricated data.

## 10. What was NOT done, and why

Steps 3 through 12 of the validation plan (fixture acceptance, identity
semantics, pipeline verification, PostgreSQL staging, failure/recovery, UI
verification against real evidence, performance measurement) **were not run.**

They are all downstream of a contract match. Running them now would produce
19 rejections and no information about the receiver's real behaviour. The stop
rule exists precisely to prevent that.

Separately and independently: **no PostgreSQL instance is available** in this
environment — no `docker`, no `psql`, no local PostgreSQL install. Even with a
matching contract, §6 could not have been executed here.
