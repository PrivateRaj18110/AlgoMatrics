# UNKNOWN / STALE implementation report

The problem this addresses, stated plainly: **before this work, a dead feed showed its last value as if it were current.** No badge, no timestamp, no indication the source had stopped talking. That is the failure mode a monitoring dashboard exists to prevent, and it was live.

---

## 1. UNKNOWN, end to end

| Layer | How UNKNOWN survives | Evidence |
|---|---|---|
| **Schema** | `{"state":"UNKNOWN","value":0}` is rejected by the published contract | `test_unknown_cannot_carry_a_value` |
| **Ingestion** | the envelope is stored verbatim; no field is normalised or defaulted | `test_unknown_survives_ingestion_storage_and_api` |
| **Database** | `envelope_json` and `observation_json` hold the message as published; no column flattens a qualified value into a scalar | same |
| **Repository** | `monitoring_store` returns `observation` as parsed JSON, untouched | `MonitoringStore._projection` |
| **Service / API** | `views.projection_view` copies the observation across without inspecting it | `test_api_serialisation_preserves_every_qualified_state` |
| **Frontend** | `QualifiedValue` renders the word `UNKNOWN` | `QualifiedValue.test.tsx` |

The receiver contains no `value_or_default`, no `coalesce`, and no `as_number` helper. Their absence is deliberate — those are the functions that turn a dead feed into a healthy-looking dashboard. `app/monitoring/qualified.py` says so in its module docstring, and `assert_preserves_states` gives the test suite a way to prove a payload round-tripped with every state intact.

All nine states are distinct in storage and on screen: `KNOWN`, `UNKNOWN`, `STALE`, `UNTRUSTED`, `INCOMPLETE`, `UNSUPPORTED`, `NOT_APPLICABLE`, `SIMULATED`, `SYNTHETIC_CLOCK`.

`UNSUPPORTED` ("this build never reports it") and `UNKNOWN` ("it should and cannot") lead to different operator actions, so they look different. `NOT_APPLICABLE` ("unfilled orders have no fill price") is not a gap at all.

## 2. STALE

The rule: `freshness.stale_after` is supplied by the publisher. After that instant the value is presented as STALE **whether or not newer data has arrived**. algomatric.in picks no timeout of its own.

Evaluated in two places, on purpose:

- **Server-side** (`app/monitoring/freshness.py`) for API consumers, attached to the response rather than written into the observation. Stored evidence keeps saying what it always said; the response says whether it may still be presented as current.
- **Client-side** (`frontend/src/lib/monitoring.ts`, re-evaluated every second) because a dashboard left open on a wall display has to cross into STALE **by itself**. If staleness were only computed at fetch time, a dead feed would keep looking live until the next poll — reintroducing the original bug at a smaller time scale.

### No horizon ⇒ UNKNOWN, not FRESH

When the publisher supplies no `stale_after`, the verdict is `UNKNOWN`, not `FRESH`. The source's FRESH was true at `data_as_of`; without a horizon there is no basis to claim it is *still* true, and defaulting to a timeout would invent the policy the contract reserves to the publisher. The UI says "no validity horizon supplied" alongside it.

This is a judgement call, and it is the conservative one. It also creates useful pressure on the publisher to supply `stale_after`.

### Dead feed (§18)

`test_dead_feed_becomes_stale_and_keeps_its_last_value` — value 100 arrives, the source stops, the publisher's horizon elapses:

```
100  STALE  LAST UPDATE: 2026-09-11 09:21:02Z
```

Not `100 LIVE`. Not `0`. The last known value stays on screen; what changes is that it stops claiming to be current. The test asserts all three: the value is still `{"state":"KNOWN","value":100}`, the freshness verdict is `STALE`, and `dataAsOf` is the source's time.

### Recovery (§19)

`test_feed_recovery_shows_no_false_continuity` — A, silence past the horizon, then B:

- during the outage the projection reads `100` with `STALE`
- after recovery it reads `250` with `FRESH` and the new `dataAsOf`
- `/history` still returns both readings with their own timestamps, so the gap between them is inspectable rather than smoothed over

No false continuity: nothing implies the feed was reporting throughout.

### Freshness is never derived from receipt time

`test_freshness_is_not_derived_from_receipt_time` — data generated yesterday, received a moment ago, reads `STALE` with `runtime: HISTORICAL`. Both facts are visible: valid as of yesterday, received just now.

## 3. What the UI does with it

`frontend/src/components/monitoring/QualifiedValue.tsx` gives each state its own treatment:

- **KNOWN** is the only state that looks like plain content
- **UNKNOWN / INCOMPLETE** — amber: something is wrong with our knowledge, not necessarily with the trading system
- **STALE / UNTRUSTED** — orange / rose: the number on screen may mislead
- **UNSUPPORTED / N/A** — quiet grey: nothing is wrong, the field does not apply
- **SIMULATED / SYNTHETIC_CLOCK** — violet: can never be mistaken for live trading

A bare scalar reaching the component renders as `UNQUALIFIED` in red rather than being displayed normally — silently accepting it would hide exactly the regression the component exists to catch.

Staleness is not conveyed by colour alone: `FreshnessBadge` renders the state as a **word** plus `LAST UPDATE: <time>`, always, for every state.

Coverage renders straight from the publisher. When `coverage.ratio` is UNKNOWN it shows UNKNOWN — never `0%`, never `100%`.

## 4. Scope boundary — the existing agent telemetry pages

`frontend/src/lib/unknown.ts` renders missing agent telemetry as an em-dash (`—`). That is **not** sufficient for monitoring.v1 — "—" reads as "nothing to report" while UNKNOWN means "the source cannot tell you, and that is the news" — so monitoring values go through `lib/monitoring.ts` instead.

The existing System Health / Machines / Events pages were **left alone**. They display the `raj_monitor` agent protocol, which has no knowledge-state vocabulary to preserve; retrofitting one would mean inventing states the agent never sent, which is precisely the reinterpretation the contract forbids. The two protocols are presented as separate pages for the same reason.

**This is a known, deliberate gap:** the legacy agent pages can still show a stale agent value as current. Fixing that requires a freshness concept in the agent protocol, which is a change to that protocol, not to this one.

## 5. Status

| | |
|---|---|
| **IMPLEMENTED** | UNKNOWN through schema → ingestion → DB → repository → API → UI; STALE from publisher-supplied horizons, re-evaluated client-side |
| **TESTED** | dead feed, recovery, absent horizon, receipt-time independence, all nine states round-tripping, 32 frontend tests |
| **VERIFIED** | end to end through the real HTTP API against a migrated database, and through rendered React components |
| **NOT DONE** | UNKNOWN/STALE for the legacy `raj_monitor` agent pages — out of scope and blocked on that protocol, see §4 |
