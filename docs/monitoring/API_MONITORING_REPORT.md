# Monitoring API report

Two API surfaces, because two different callers need different things.

## 1. ops-api — `/api/v1/monitoring/*`

The receiver's own API. Public path `/ops/api/v1/monitoring/*` via the existing nginx proxy.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/export` | publisher (upload-only, source-scoped) | the ingress |
| GET | `/state` | dashboard viewer | current projections + freshness verdicts |
| GET | `/state/{kind}` | dashboard viewer | one observation kind |
| GET | `/evidence/{message_id}` | dashboard viewer | one received message, as stored |
| GET | `/history` | dashboard viewer | evidence history for an entity, oldest first |
| GET | `/sources` | dashboard viewer | publisher delivery health, gaps included |
| GET | `/conflicts` | dashboard viewer | contradictions, both sides |
| GET | `/health` | none | receiver health — **not** LLS health |
| GET | `/quarantine` | **administrator** | material that never entered a projection |

Exactly one write operation exists, and it writes observations. `test_monitoring_routes_expose_no_control_actions` asserts this against the published OpenAPI surface, not the in-memory router tree.

## 2. Platform API — `/api/v1/operations/monitoring/*`

What the production UI actually calls. The platform backend reads the ops database read-only, the same pattern the existing operations pages use.

| Path | Purpose |
|---|---|
| `/operations/monitoring/state` | current projections |
| `/operations/monitoring/sources` | delivery health |
| `/operations/monitoring/conflicts` | contradictions |
| `/operations/monitoring/history` | evidence history |

All gated by the existing `TRADING_VIEW` permission and tenant context. All read-only — there is no write, acknowledge, or resolve operation anywhere in this path.

## 3. Every response retains provenance

A number without context is the thing this system exists to stop shipping. Each item carries:

```json
{
  "source_id": "...", "source_instance": "...", "sequence": 90211,
  "message_id": "...", "revision": 0, "schema_version": "1.0",
  "runtime": "LIVE", "environment": "production",
  "source_time": "...", "generated_at": "...", "data_as_of": "...",
  "stale_after": "...", "received_at": "...",
  "declared_freshness_state": "FRESH", "trust_level": "AUTHORITATIVE",
  "has_conflict": false,
  "observation": { "kind": "...", "qualifiers": {...}, "payload": {...} }
}
```

Five distinct instants, never collapsed into one "timestamp". `source_time` is the source's clock, `generated_at` is when Monitoring produced the message, `data_as_of` is what it is valid as of, `received_at` is stamped by the receiver, and display time is the browser's.

`observation` is **verbatim**. Qualified values arrive as they were published.

## 4. Where freshness is decided

ops-api attaches a server-side verdict for API consumers. The platform read path deliberately does **not** — it passes `stale_after` through and the browser evaluates it on every render.

The reason is not symmetry but correctness: a verdict computed at fetch time is frozen, and a dashboard left open would keep showing FRESH after the horizon elapsed. The client re-evaluates every second, so a dead feed turns STALE on screen without a refetch.

## 5. `configured` vs empty

`/operations/monitoring/state` returns `configured` explicitly. "No monitoring data has arrived" and "this deployment has no monitoring database" are different facts that an empty list alone conflates, and an operator would act differently on each. The UI renders them differently.

## 6. Serialisation preserves knowledge states

`test_api_serialisation_preserves_every_qualified_state` walks the published observation and the API response and asserts the `(path, state)` pairs are identical. `test_every_knowledge_state_round_trips_through_the_api` covers `KNOWN`, `UNKNOWN`, `STALE`, `UNTRUSTED`, `INCOMPLETE`, `SIMULATED` and `SYNTHETIC_CLOCK` individually, asserting that states without a value have no `value` key on the way out.

## 7. Status

| | |
|---|---|
| **IMPLEMENTED** | both surfaces, all endpoints above |
| **TESTED** | ops-api endpoints exercised through `TestClient` against a migrated database; the platform read layer covered by 11 tests in `tests/unit/test_monitoring_read_path.py` (qualified-value survival, environment isolation, unevaluated `stale_after`, gap reporting, corrupt-row degradation) |
| **NOT TESTED** | the four platform FastAPI route functions themselves — thin passthroughs over the tested `MonitoringStore`, typecheck-clean, but no request-level test asserts permission gating on them specifically |
| **UNKNOWN** | response size at production volume; `/state` caps at 1000 rows but observations are unbounded in width |
