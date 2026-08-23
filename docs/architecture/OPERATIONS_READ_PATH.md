# Operations read path (main /app)

**Invariant:** commit `f9bee1a` is preserved. Ingest classification is unchanged.
`heartbeat`, `strategy_status`, `system_status`, and `order` are never Closed Trades.
Only `trade` / `trade_closed` create blotter rows.

## Data flow

```
Google VM + X-Raj-Agent-Token
        ↓
ops-api  POST /ops/api/agent/batch   (ingestion; keep this)
        ↓
Ops PostgreSQL                       (machines, events, trades, logs)
        ↓
algo-api GET /api/v1/operations/*    (main JWT + X-Org-Id + trading:view)
        ↓
/app SPA                             (user-facing analysis)
```

`/ops` remains until Google → /app is verified in production. Do not delete
`ops/backend`, `ops/frontend`, or agent endpoints.

## Why ops-api still exists

Google currently ships telemetry to ops-api. The main API is a **read layer**
over that database. There is no second ingestion path and no browser ingest
credential.

## Authentication

The browser uses the existing AlgoMatrics session: access JWT (Authorization
Bearer) plus `X-Org-Id`. WebSockets use `POST /api/v1/auth/ws-ticket`.

Never put these in the frontend bundle:

- `RAJ_AGENT_TOKEN` / `RAJ_AGENT_TOKENS` / `X-Raj-Agent-Token`
- `RAJ_DASHBOARD_TOKEN`
- `VITE_OPS_API_TOKEN` / `VITE_OPS_WS_TOKEN`
- `DATABASE_URL` / `OPS_DATABASE_URL`
- `ALGOMATRICS_API_KEY`

`OPS_DATABASE_URL` is server-side only (`algo_platform.config.Settings`).

## Fail-closed behaviour

| Condition | Response |
|---|---|
| `OPS_DATABASE_URL` unset, `APP_ENV=production` | `503 unavailable` |
| `OPS_DATABASE_URL` unset, local/test | `[]` / empty overview, never fixtures |
| Database configured, no rows | `[]` |
| Database error | `503 unavailable` |

Production must not fall back to Mean Reversion FX, Gold Scalper, London VPS,
IC Markets, Binance, or generated PnL.

## Strategy → symbol

Google does not send a strategy dimension table. Identity is
`{machine_id}::{strategy_name}` when both are present; missing machine does
not invent `"unknown"`. Missing strategy/symbol stay `null`.

Analytics:

- platform totals
- strategy
- strategy × symbol
- symbol × strategy (`GET /api/v1/operations/symbols` and analytics `by_symbol`)
- individual classified trades

## Option / instrument metadata

Producer envelopes currently send `symbol` as a string. They do **not** send
`underlying`, `instrument`, `option_type`, `strike`, `expiry`, or
`instrument_token`. Those API fields are nullable.

Optional parse of `NIFTY 24500 CE` style text exists only when that pattern is
present, covered by unit tests. Equity symbols such as `RELIANCE` stay
unparsed.

## Timestamps

Canonical storage and API: ISO-8601 UTC (`…Z`).

| Field | Source |
|---|---|
| `event_ts` / `time` | `events.time` (producer/event clock) |
| `ingest_ts` / `received_at` | `events.created_at` (ops-api insert) |
| `trade_ts` / `time` | `trades.time` |
| `exchange_ts` | not in current telemetry; omitted |

Frontend display: IANA `Asia/Kolkata` and `UTC`. Never add/subtract 5:30.

## Historical blotter

Likely-misclassified heartbeat rows remain in Ops Postgres. The read API
filters them from analytics; it does not delete them.

## Demo / seed data exclusion

Historical demo fixtures (London VPS, Personal Computer, Mean Reversion FX, Gold Scalper, IC Markets, trades without `envelope_id`, `live=False` machine placeholders) are excluded at the read layer from `/api/v1/operations/*` endpoints.

The operations read path guarantees that only live Google telemetry (`live=True`, valid `envelope_id`, real strategy identities) is served to the application.

## Database / migrations

No new tables. Main algo-api reads the existing ops schema.

## Production go-live (not claimed here)

1. Set `algo-secrets.OPS_DATABASE_URL` to the ops Postgres URL.
2. Deploy this branch so `/api/v1/operations/*` exists.
3. Verify the same Google machine on ingest and `/app`.
4. Only then consider retiring the `/ops` **frontend**. Keep ingest.
