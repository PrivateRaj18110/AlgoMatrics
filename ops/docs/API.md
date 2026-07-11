# API Reference

Base URL: `http://localhost:8000` · API prefix: `/api` · Interactive docs: `/docs` (Swagger), `/redoc`.

All data is served from in-memory mock repositories; responses match the TypeScript types in
`frontend/src/types`. Switching to Supabase later changes only the repository implementations.

---

## System

| Method | Path          | Response | Notes |
| ------ | ------------- | -------- | ----- |
| GET    | `/`           | `{ service, version, docs, health }` | Service root |
| GET    | `/api/health` | `{ status, version, time, environment }` | Liveness probe |
| WS     | `/api/ws`     | stream of `RealtimeMessage` | Live feed (see below) |

## Trading

| Method | Path                      | Response            |
| ------ | ------------------------- | ------------------- |
| GET    | `/api/dashboard/overview` | `DashboardOverview` (`kpis`, `equityCurve`, `dailyPnl`, `performance`) |
| GET    | `/api/strategies`         | `Strategy[]`        |
| GET    | `/api/strategies/{id}`    | `Strategy` (404 if missing) |
| GET    | `/api/trades`             | `Trade[]` — supports `?limit=` |
| GET    | `/api/execution/overview` | `ExecutionData` (`stages`, `latency`, `recent`, `throughput`) |
| GET    | `/api/risk/overview`      | `RiskData` (loss limits, exposure breakdowns, drawdown, VaR) |
| GET    | `/api/analytics`          | `AnalyticsData` (series + heatmaps) |

## Infrastructure

| Method | Path                  | Response       |
| ------ | --------------------- | -------------- |
| GET    | `/api/machines`       | `Machine[]`    |
| GET    | `/api/machines/{id}`  | `Machine`      |
| GET    | `/api/brokers`        | `Broker[]`     |
| GET    | `/api/brokers/{id}`   | `Broker`       |
| GET    | `/api/accounts`       | `Account[]`    |
| GET    | `/api/accounts/{id}`  | `Account`      |

## Operations

| Method | Path             | Response          | Query |
| ------ | ---------------- | ----------------- | ----- |
| GET    | `/api/events`    | `SystemEvent[]`   | `limit` (1–400, default 200) |
| GET    | `/api/logs`      | `LogEntry[]`      | `source` (application/strategy/python/broker/database/system), `limit` |
| GET    | `/api/alerts`    | `Alert[]`         | — |
| GET    | `/api/settings`  | `AppSettings`     | — |
| PUT    | `/api/settings`  | `AppSettings`     | body: `AppSettings` |

## SDK ingestion (`monitor_sdk`)

All accept the common identity envelope (`strategy`, `machine`, `account?`, `token?`, `ts?`) plus the
method-specific fields, and return `IngestAck = { accepted, received, kind }`. See
[`SDK_Integration.md`](SDK_Integration.md).

| Method | Path                     | Payload            |
| ------ | ------------------------ | ------------------ |
| POST   | `/api/ingest/start`      | `StartPayload`     |
| POST   | `/api/ingest/heartbeat`  | `HeartbeatPayload` |
| POST   | `/api/ingest/trade`      | `TradePayload`     |
| POST   | `/api/ingest/position`   | `PositionPayload`  |
| POST   | `/api/ingest/metric`     | `MetricPayload`    |
| POST   | `/api/ingest/event`      | `EventPayload`     |
| POST   | `/api/ingest/error`      | `ErrorPayload`     |

---

## Websocket protocol

Connect to `ws://localhost:8000/api/ws`. On connect the server sends a machine snapshot, then streams:

```jsonc
{ "type": "machines",   "payload": [ /* Machine[] */ ] }      // ~3s telemetry refresh
{ "type": "event",      "payload": { /* SystemEvent */ } }    // live events (incl. SDK ingest)
{ "type": "connection", "payload": { "latencyMs": 8, "time": "<iso>" } }  // heartbeat
```

The frontend folds `machines` and `event` messages straight into the TanStack Query cache, so any open
page updates automatically. In mock mode the identical protocol is produced by an in-browser engine, so
no backend is required for the live feel.

---

## Examples

```bash
curl http://localhost:8000/api/dashboard/overview | jq '.kpis[0]'
curl "http://localhost:8000/api/trades?limit=3" | jq '.[0]'
curl "http://localhost:8000/api/logs?source=broker&limit=5" | jq

curl -X POST http://localhost:8000/api/ingest/trade \
  -H 'Content-Type: application/json' \
  -d '{"strategy":"MR-FX","machine":"London VPS","symbol":"EURUSD","direction":"long","entry":1.085,"exit":1.089,"quantity":1.0,"pnl":320.0,"status":"closed"}'
```
