# Observability (Phase 1)

Enterprise observability for Algo Matrics: metrics, dashboards, logs, and
alerting. This document is the operator runbook for the stack delivered in
Phase 1.

## Architecture

```
 API process ──/metrics──┐
 worker    ──:9100/metrics┤
 engine    ──:9100/metrics├──▶ Prometheus ──▶ Alertmanager ──▶ Slack
 market-data──:9100/metrics┤        │
 scheduler ──:9100/metrics┘        └────────────▶ Grafana ◀── Loki ◀── Promtail
 cadvisor / node-exporter ─────────┘                              (container logs)
```

- **Metrics** — Every process owns a private Prometheus registry
  (`shared/infrastructure/prometheus.py`). The API exposes it at the root
  `/metrics`; background processes serve it on `METRICS_PORT` (default `9100`)
  via `shared/infrastructure/metrics_server.py`.
- **Logs** — `structlog` emits JSON in non-local environments. Promtail tails
  container logs and ships them to Loki, promoting `service`, `level`, and
  `correlation_id` to labels.
- **Correlation** — Every HTTP request carries `X-Request-ID` and
  `X-Correlation-ID` (accepted from upstream or generated). The SPA sends a
  stable per-tab `X-Correlation-ID`, so a user action can be traced across the
  frontend, API, and logs. Both are bound into the structured log context.

## Running the stack locally

```bash
cd deploy/compose
docker compose \
  -f docker-compose.yml \
  -f docker-compose.observability.yml \
  up -d
```

| Tool         | URL (localhost)     | Notes                                   |
|--------------|---------------------|-----------------------------------------|
| Grafana      | http://localhost:3000 | admin / `GRAFANA_ADMIN_PASSWORD`      |
| Prometheus   | http://localhost:9090 | targets at /targets                   |
| Alertmanager | http://localhost:9093 |                                       |
| Loki         | http://localhost:3100 | queried through Grafana                |

Grafana auto-provisions the Prometheus + Loki datasources and three dashboards
(**API Latency & Errors**, **Trading / Orders / P&L**, **Infrastructure &
Queues**) from `deploy/observability/grafana`.

Ports bind to `127.0.0.1` only. In production, publish them exclusively through
an authenticated reverse proxy and keep `/metrics` on a private network.

## Metric catalogue (namespace `algo`)

| Area        | Metric                                   |
|-------------|-------------------------------------------|
| HTTP        | `http_requests_total`, `http_request_duration_seconds`, `http_requests_in_progress` |
| Trading     | `orders_submitted_total`, `orders_filled_total`, `orders_rejected_total`, `positions_open`, `pnl`, `strategy_runs_active` |
| Brokers     | `broker_requests_total`, `broker_request_duration_seconds`, `broker_up` |
| Streams     | `stream_depth`, `events_published_total`, `events_consumed_total` |
| Market data | `market_ticks_total`, `engine_tick_duration_seconds` |
| Infra       | `db_pool_connections`, `redis_up`, process CPU/memory |
| WebSocket   | `ws_connections`, `ws_messages_total`     |
| Frontend    | `frontend_web_vitals`, `frontend_errors_total` |

All labels are low cardinality (route templates, broker slugs, enum values).
Order counters are derived centrally by the outbox worker from relayed domain
events (`shared/infrastructure/metrics_events.py`), so no domain service depends
on the metrics layer.

## Dashboards are reproducible

Dashboards are generated, not hand-edited:

```bash
python scripts/observability/gen_dashboards.py deploy/observability/grafana/dashboards
```

## Alerts

Rules live in `deploy/observability/prometheus/alerts.yml`: process down, API
error-rate / p95 latency SLOs, order-rejection spikes, broker down, engine tick
stall, stream backlog, Redis down, and DB pool exhaustion. Alertmanager routes
critical alerts to Slack via `ALERT_SLACK_WEBHOOK_URL` (no secrets in the repo).

## Rollback

The stack is additive and isolated:

- **Disable instrumentation without redeploying code:** set `METRICS_ENABLED=false`.
  The `/metrics` endpoint returns 404, the infra sampler and process metric
  servers do not start, and all instrumentation guards short-circuit.
- **Remove the stack:** `docker compose -f docker-compose.yml -f
  docker-compose.observability.yml down` (omit the override to stop only the
  monitoring tools while the app keeps running).
- **Revert the code:** the work is isolated to the `phase-1-observability`
  branch; `git revert` of the slice commits restores the prior behaviour. No
  database migration or API-contract change is involved, so rollback is safe at
  any time.
