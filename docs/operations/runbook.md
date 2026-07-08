# Operations runbook

## Services

| Service | Command | Role |
|---|---|---|
| `api` | `entrypoint.sh api` | FastAPI control plane + WebSocket hub |
| `worker` | `entrypoint.sh worker` | Transactional-outbox relay to Redis Streams |
| `market-data` | `entrypoint.sh market-data` | Simulated tick/candle feed publisher |
| `trading-engine` | `entrypoint.sh engine` | Paper fills, live routing, strategy runtimes, snapshots |
| `scheduler` | `entrypoint.sh scheduler` | Billing rollovers, token/session hygiene |
| `migrate` | `entrypoint.sh migrate` | One-shot Alembic upgrade + seed |
| `frontend` | nginx | Serves the SPA and proxies `/api` + WebSocket |

## Health

- Liveness: `GET /api/v1/health/live`
- Readiness (DB + Redis): `GET /api/v1/health/ready`
- Platform admin dashboard: `GET /api/v1/admin/health` returns DB/Redis status,
  outbox backlog, and process heartbeat ages.

Each background process writes a heartbeat to Redis (`hb:market_data`,
`hb:trading_engine`, `hb:worker`, `hb:scheduler`) with a 120–300s TTL. A missing
heartbeat in the admin health view means that process is down.

## Common tasks

Run migrations manually:

```bash
docker compose -f deploy/compose/docker-compose.yml run --rm migrate
```

Re-seed reference data (idempotent — existing rows untouched):

```bash
docker compose -f deploy/compose/docker-compose.yml exec api python scripts/seed.py
```

Promote / demote a platform admin:

```bash
docker compose -f deploy/compose/docker-compose.yml exec api \
  python scripts/promote_admin.py user@example.com [--revoke]
```

## Payments

- Configure `RAZORPAY_*` and/or `STRIPE_*` in `.env` to enable paid checkout.
  Without them, Free and fully-coupon-covered plans still work.
- Webhook endpoints (provider-authenticated, no user auth):
  `POST /api/v1/billing/webhooks/razorpay` and `.../stripe`. Point the provider
  dashboards at these and set the matching `*_WEBHOOK_SECRET`.
- Payments are idempotent by `(provider, provider_payment_id)`; webhook retries
  are safe.

## Incident: engine not filling paper orders

1. Check `GET /api/v1/admin/health` — is `market_data_age_seconds` fresh?
2. Confirm the `market-data` and `trading-engine` containers are running.
3. Inspect the Redis command stream depth (`XLEN engine:commands`).
4. The engine reconciles open orders on restart; a restart is safe.

## Incident: daily-loss kill switch tripped

The engine auto-pauses strategy runs on an account whose realized daily loss
breaches `max_daily_loss`. Review `GET /api/v1/risk/violations`, adjust limits if
appropriate, then resume runs from the strategy detail page.

## Backups

PostgreSQL is authoritative. Use managed PITR (continuous WAL + daily snapshots)
in production. Redis is reconstructable — no irreplaceable state lives only there.
After a restore, broker reconciliation rebuilds external truth.
