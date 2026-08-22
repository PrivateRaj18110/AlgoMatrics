# AlgoMatrics architecture audit (Phase 1)

**Status:** implementation of the main `/app` read path is documented in
[`OPERATIONS_READ_PATH.md`](./OPERATIONS_READ_PATH.md). This audit remains the
source-backed map of the two-app surface.
**Classification invariant:** commit `f9bee1a` (`fix(ops): classify telemetry so only real trades hit Closed Trades`).
**Historical blotter:** ~1463 trade rows / ~1367 likely misclassified — **do not delete**.

This document is the source-backed map of the current two-app production surface and the target single-app architecture. Implementation starts at Phase 2.

---

## 1. Current architecture

```
Browser
  ├─ https://algomatrics.in/app/*     main console SPA  →  /api/v1  →  algo-api (JWT + org)
  └─ https://algomatrics.in/ops/*     Raj Quant OS SPA  →  /ops/api →  ops-api
                                                              │
Google VM DataAgent ──X-Raj-Agent-Token──► /ops/api/agent/batch
                                                              │
                                                    ops telemetry Postgres
```

| Surface | Location | Auth | Data |
|---|---|---|---|
| Main SPA | `frontend/` served at `/` and `/app` | Login + httpOnly refresh + Bearer access JWT + `X-Org-Id` | Platform DB via `/api/v1` |
| Ops SPA | `ops/frontend/` `base: '/ops/'` | Shared `VITE_OPS_*` token in the JS bundle | Mix of live telemetry + **always-mock** fixtures |
| Platform API | `backend/` `algo-api` | Per-user JWT, org RBAC, WS ticket | Trading SaaS models |
| Ops API | `ops/backend/` `ops-api` | Agent token (ingest); dashboard token or JWT (reads/WS) | Telemetry DB + in-memory mocks |
| Google agent | `packages/raj_monitor` + VM PerformanceMonitor | `X-Raj-Agent-Token` (server-side on the VM) | Heartbeat / status / order / trade envelopes |
| Edge | `deploy/nginx/nginx.conf` | N/A | `/api/` → algo-api; `/ops/api/` → ops-api; `/ops/` static SPA |

Nginx (`deploy/nginx/nginx.conf`) publishes **two** user-facing apps from one frontend image (`deploy/docker/frontend.Dockerfile` copies main `dist` to `/` and ops `dist` to `/ops`).

### What is actually real today

Verified ingest path (do not regress):

- Google agent → `POST /ops/api/agent/batch`
- `ops-api` persists machines, events, metrics, **explicit trades only** (`f9bee1a`)
- Heartbeats update `lastHeartbeat` / `lastSuccessfulUpload` / queue
- `system_status`, `strategy_status`, `order`, `trade` events are classified separately

### What is still fake on `/ops`

Even with live ingest, many pages do **not** read the telemetry tables:

| Endpoint | Production behaviour |
|---|---|
| `GET /api/strategies` | `algomatrics_service.strategies()` **or** in-memory `STRATEGIES` (Mean Reversion FX, Gold Scalper, …) |
| `GET /api/brokers` | live platform brokers **or** IC Markets / Pepperstone / IB / Binance fixtures |
| `GET /api/dashboard/overview` | live platform KPIs **or** generated equity/PnL |
| `GET /api/analytics/*`, `/risk`, `/execution` | **always** mock documents (`execution_doc`, `analytics_doc`, `risk_doc`) |
| `GET /api/alerts`, `/accounts` | **always** in-memory mock lists |
| `GET /api/trades` | telemetry blotter **plus** `seed_if_empty()` demo trades if the table was empty at first boot; also `algomatrics_service.trades()` if `ALGOMATRICS_*` is set (platform fills, not Google closed trades) |

`strategies_repo`, `brokers_repo`, `accounts_repo`, `alerts_repo`, and the dashboard/analytics/risk/execution documents are **explicitly always-mock** in `ops/backend/app/repositories/__init__.py` (“out of scope for the DB migration”).

Startup still calls `seed_if_empty()` (`ops/backend/main.py`), which inserts London VPS / demo trades when those tables are empty.

---

## 2. Target architecture

```
Browser (one SPA: /app)
        ↓  session JWT (never an ingest or shared dashboard secret)
Main AlgoMatrics API  (/api/v1)
        ↓  internal, server-side
Telemetry read models  ←  ops telemetry Postgres  ←  Google DataAgent (/ops/api/agent/* kept as infrastructure)
Platform trading models ←  platform Postgres
```

Rules:

- **One** user-facing app: `/app`.
- **Do not** iframe or redirect `/app` ↔ `/ops`.
- Google ingest stays on `ops-api` (or a future merged service) with **server-side** agent tokens.
- Browser talks only to `/api/v1` using the existing login session.
- Missing telemetry → empty/unknown UI, never fixtures.
- Closed Trades ← `event_type=trade` / `source_event_type=trade_closed` only (`f9bee1a`).
- Canonical timestamps: timezone-aware UTC in storage and APIs; IST (and optional UTC) in the UI via IANA timezone, never `+5:30` arithmetic.

### Proposed `/app` mapping (reuse existing routes where they exist)

| Capability | Existing `/app` | Existing `/ops` | Target |
|---|---|---|---|
| Dashboard | `/app/dashboard` | `/ops/` | Extend main dashboard with Google machine + real PnL |
| Strategies | `/app/strategies`, `/app/strategies/:id` | `/ops/:market/strategies` | Add `/app/strategies/:id/:symbol` when identity exists |
| Positions / orders / trades | `/app/trading/*` | live/closed trades | Same URLs; back with Google+platform truth |
| Machines | none | `/ops/monitoring` | `/app/machines` (new) |
| Events / logs / alerts | notifications/audit | `/ops/events`, logs, alerts | `/app/events`, `/app/logs`, `/app/alerts` |
| Execution / risk / analytics | trading tabs + `/app/analytics` | market pages | Keep `/app` paths; swap mock sources |
| Brokers | `/app/settings/brokers` | `/ops/:market/brokers` | Settings brokers only; no IC Markets fixtures |
| Ops SPA | — | `/ops/*` | Keep until Phase 6; then deprecate |

---

## 3. Files changed (this phase)

| File | Change |
|---|---|
| `docs/architecture/ARCHITECTURE_AUDIT.md` | This audit |

No application, nginx, or Google agent code was modified.

---

## 4. Fake data sources found

### Ops frontend (`ops/frontend/src/services/mock/` and `USE_MOCK`)

- `machines.mock.ts` — London VPS, Google Cloud, Personal Computer
- `strategies.mock.ts` — NIFTY Options Scalper, BankNifty Momentum, Mean Reversion FX-class names on international book
- `trades.mock.ts`, `brokers.mock.ts`, `accounts.mock.ts`, `alerts.mock.ts`, `risk.mock.ts`, `dashboard.mock.ts`, `execution.mock.ts`, `events.mock.ts`, `logs.mock.ts`
- `realtime/engine.ts` — jittered CPU/RAM and synthetic events
- `api/client.ts` — `USE_MOCK = VITE_USE_MOCK === 'true' || API_BASE_URL === ''` (empty base URL silently mocks)

Production image sets `VITE_API_BASE_URL=/ops/api` and `VITE_USE_MOCK=false`, so the **SPA is live**, but it still displays backend mocks for strategies/brokers/analytics.

### Ops backend

- `ops/backend/app/repositories/mock_data.py` — London VPS; IC Markets, Pepperstone, Interactive Brokers, Binance; Mean Reversion FX, Momentum Breakout, Gold Scalper, Stat Arb Pairs, Crypto Trend, Index Overnight, News Fade, Grid Hedge, Vol Harvest; RNG PnL/win rate/latency/equity
- `ops/backend/app/database/seed.py` — seeds those machines/trades into Postgres if empty
- Always-mock repos: strategies, brokers, accounts, alerts, dashboard/analytics/risk/execution docs
- `algomatrics_service.py` — if `ALGOMATRICS_*` unset or upstream fails, **falls back to those mocks** (documented as graceful)
- `realtime/publisher.py` — still broadcasts; in DB mode it does not jitter live machines, but mock mode fabricates events

### Main app

- Main dashboard uses `/api/v1` (not ops mocks). Empty org/account state can look sparse; that is preferable to ops fixtures.
- `toLocaleString(undefined, …)` in `frontend/src/lib/format.ts` uses **browser local** time, not a selected IST/UTC display zone.

---

## 5. Fake data sources removed

**None in this phase** (audit only). Phase 2 must fail closed to empty instead of `strategies_repo.list()` / `seed_if_empty()`.

---

## 6. Real data sources identified

| Domain | Source of truth | Store / API today |
|---|---|---|
| Machine liveness, queue, upload | Google heartbeat / `system_status` | `machines` table; `GET /ops/api/machines` |
| Strategy runtime status | Google `strategy_status` events | `events.event_type='strategy_status'` — **not** a strategy dimension table |
| Orders | Google `order` events | `events.event_type='order'` — **no orders table** |
| Closed trades | Google `trade` / `trade_closed` | `trades` table after `f9bee1a` |
| Generic telemetry | heartbeat, system_status, errors, logs | `events`, `logs`, `metrics` |
| Platform accounts, SaaS strategies, billing | AlgoMatrics control plane | `/api/v1` platform DB — **different grain** from Google engine instances |
| Historical corrupted blotter | Misclassified telemetry (pre-`f9bee1a`) | `trades` — preserve; separate cleanup plan |

**Strategy identity gap:** there is no durable `strategies` table populated from Google. `strategyCount` on the machine row is whatever the heartbeat payload sends. The UI strategy list is mock or SaaS `/strategies`, not DataAgent instances.

**Symbol / option gap:** order/trade payloads may include `symbol`. There is no first-class underlying / strike / CE-PE / expiry / token model on AWS. Phase 4 must inventory real envelope `data` keys from production events before adding fields.

---

## 7. Authentication / security findings

### Main app (stronger model — keep)

- Login at `/login`; access token in memory; refresh via `POST /api/v1/auth/refresh` with `credentials: "include"`
- Org header `X-Org-Id`
- Websocket: `POST /api/v1/auth/ws-ticket` then ticketed `/api/v1/ws` (no long-lived secret in JS)
- CORS via FastAPI; security headers on nginx
- CSRF: cookie refresh is same-origin; SPA uses Bearer for API (not a classic form CSRF surface)

### Ops app (must not remain the user auth boundary)

| Issue | Evidence | Severity |
|---|---|---|
| Privileged/shared viewer secret compiled into JS | `VITE_OPS_API_TOKEN` / `VITE_OPS_WS_TOKEN` in `ops/frontend/src/services/api/client.ts` and `realtime/socket.ts` | **Critical** if set at image build |
| Dockerfile does not currently pass those ARG/ENV | `deploy/docker/frontend.Dockerfile` only sets `VITE_API_BASE_URL` + `VITE_USE_MOCK` | Production may rely on unauthenticated REST in some envs, or inject tokens elsewhere |
| Shared `RAJ_DASHBOARD_TOKEN` authenticates “a dashboard”, not a person | `ops/backend/app/api/dependencies/dashboard_auth.py` | High |
| REST auth optional unless production / `OPS_REST_AUTH_REQUIRED` | `rest_auth_required()`; compose default `OPS_REST_AUTH_REQUIRED=false` | High in non-k8s |
| K8s sets `OPS_REST_AUTH_REQUIRED=true` | `deploy/k8s/45-ops.yaml` | Good for cluster |
| JWT path exists (`OPS_JWT_PUBLIC_KEY`) but ops SPA does not use main login | dashboard_auth.py | Unused preferred path |
| Agent ingest tokens stay server-side | `X-Raj-Agent-Token` on VM → ops-api | **Keep** |
| `RAJ_AGENT_TOKEN` must never ship in Vite | not in ops frontend env example as VITE_AGENT | Confirm in CI/secrets |

**Target:** browser never sees `RAJ_AGENT_*` or `RAJ_DASHBOARD_TOKEN`. Main `/api/v1` session authorizes telemetry **reads**. Ingest remains machine-scoped agent tokens.

---

## 8. Timestamp findings

| Layer | Practice | Gap |
|---|---|---|
| Ops DB | `DateTime(timezone=True)`, `utcnow()` | Good UTC storage |
| Ops ingest | `env.ts` parsed; naive → UTC; persist `_now_iso()` on some trade rows | Trade **row time** can be **server receive time**, not envelope/exchange time |
| Ops API | ISO strings from `_iso()` | Often `+00:00`, not always `Z` |
| Ops UI | `toLocaleString('en-US')` / `toLocaleTimeString('en-GB')` **without `timeZone`** | Browser local, not IST |
| Settings | `timezone: 'utc'` exists but formatters ignore it | Dead setting |
| Main UI | `dateTime()` uses `toLocaleString(undefined)` | Browser local |
| Dual timestamps | No `exchange_time` vs `received_at` on trades | Latency analysis cannot separate them |

Phase 2: persist envelope `ts` as event time; `created_at` as receive time; API always UTC ISO; UI `Intl` with `Asia/Kolkata` or `UTC`.

---

## 9. Strategy data source (current vs required)

**Current:** mock `STRATEGIES` or SaaS `/api/v1/strategies` via `ALGOMATRICS_*` proxy.  
**Required:** Google runtime identity (name / instance / id / machine / session / symbols) from `strategy_status` (and start/stop).  
**If `strategyCount` is wrong:** fix the heartbeat payload contract on the VM; do not invent rows.

---

## 10. Symbol / sub-symbol data source

**Current:** free-text `symbol` on events/trades when the agent sends it.  
**Required:** discover actual keys from live `order` / `trade` payloads (do not invent strike/expiry). If missing, smallest Google extension: underlying, expiry, strike, option_type, instrument/token.

---

## 11. API changes (planned, not done)

- Add `/api/v1/ops/*` (or equivalent) on **algo-api**, authenticated like the rest of `/api/v1`, proxying/reading telemetry DB.
- Stop returning mock documents from ops-api in production.
- Filter `GET /api/trades` to classified trades only (already ingest-side); hide/archive historical junk later.
- Do not expose `/ops/api` to the browser after Phase 3 (ingest can remain on a non-browser path).

---

## 12. Routes added/changed

None in this phase.

---

## 13. Ops routes remaining

All of `/ops/*` remain in production until Phase 6. Ingest `/ops/api/agent/*` remains as infrastructure even after the Ops SPA is removed.

---

## 14–16. Tests

**Not re-run in this audit-only phase.** Last known relevant results (prior session):

- `tests/test_telemetry_classification.py` — 15 passed
- `test_agent_compatibility`, `test_phase3_status_timeline`, `test_ws_auth` — passed

Phase 2+ must re-run classification, agent auth, WS auth, main frontend tests, lint, typecheck, and add: no production mock fallback; order ≠ trade; no VITE privileged token; UTC timestamps.

---

## 17. Database migrations required?

- **Not for ingest classification** (already shipped).
- **Likely later:** strategy identity table; `exchange_time` vs `received_at` on trades/events; optional archive table for misclassified blotter rows.
- **Do not** migrate/delete the 1367 suspect trades in the unification PRs.

---

## 18. Historical corrupted trades

Preserve. Matching criteria from the read-only auditor (`ops/backend/scripts/audit_misclassified_trades.py`): unknown/empty strategy, entry 0, null exit, pnl 0, duration 0, status closed. Separate cleanup plan after the unified `/app` reads only post-`f9bee1a` trades (e.g. `created_at` / envelope metadata). **No DELETE in this workstream.**

---

## 19. Deployment changes required (later phases)

- Stop baking `VITE_OPS_*` tokens if any pipeline sets them.
- Frontend image: eventually drop `ops-builder` stage and `/ops` nginx locations.
- Keep `ops-api` Deployment for agent ingest (or merge ingest into algo-api without changing Google URL without a coordinated VM change).
- Prefer **not** changing Google `RAJ_BACKEND` URL until a reverse-proxy alias exists.
- Nginx: `/app` already served by main SPA; add API routes under `/api/v1`, not a second dashboard.

---

## 20. Git commits

| Commit | Note |
|---|---|
| `f9bee1a` | Telemetry classification — **do not revert** |
| this audit | Documentation only when committed |

---

## Phase plan (do not skip)

1. **Audit** — this document.
2. **Foundation** — production fail-closed (no mock/seed), no browser secrets, UTC+display TZ, keep `f9bee1a`.
3. **Integrate** — main `/app` reads telemetry via `/api/v1`; empty states; no iframe.
4. **Analytics** — strategy → symbol → instrument from real payloads.
5. **Validate** — the 17 success checks in the product brief.
6. **Deprecate `/ops` SPA** — keep ingest.

### Success criterion (not “UI looks full”)

Real Google VM data → AWS telemetry store → authenticated main AlgoMatrics API → one `/app` UI.  
No fake brokers/strategies/PnL. No duplicate production dashboard. No privileged tokens in JavaScript. No order→trade. No timezone ambiguity.
