# Algo Matrics Platform

A production-grade, **enterprise** multi-tenant algorithmic trading platform:
strategies, brokers, risk controls, SaaS billing, real-time P&L, and a full
operations stack in one console.

The repository is a monorepo built on **Clean Architecture** and **Domain-Driven
Design** as a modular monolith plus specialized runtimes:

- a **FastAPI control plane** (`/api/v1`) with JWT + rotating refresh tokens, RBAC,
  RFC 9457 errors, OWASP security headers, and per-organization IP allowlisting;
- independently runnable **trading engine**, **market-data**, **worker** (role-based),
  and **scheduler** processes, coordinated through an **event bus** (Redis Streams);
- a broker-neutral **strategy SDK** with sandboxed uploads, semantic **versioning**,
  approvals, and deployment history;
- a **React + TypeScript operations console** (Vite, Tailwind 4, TanStack Query);
- a **full observability stack** (Prometheus/Grafana/Loki/Alertmanager) plus
  circuit breakers, deep readiness probes, and backlog-driven autoscaling;
- **Docker Compose** for local/one-command bring-up and **Kubernetes** manifests
  (+ KEDA/HPA) for production.

The canonical design is in [`docs/architecture/FOUNDATION.md`](docs/architecture/FOUNDATION.md);
per-capability operations guides live in [`docs/operations/`](docs/operations).

## What a user can do

1. Register an account and verify their e-mail.
2. Log in securely (with optional TOTP MFA) — on web or mobile (device registry + push).
3. Subscribe to a plan (Free / Starter / Pro / Enterprise) via Razorpay or Stripe,
   with GST/tax and refunds.
4. Connect a broker — Paper Trading, Zerodha, Angel One, or **Flattrade**
   (Delta, Binance, Interactive Brokers, and MT5 adapters remain in the
   codebase but are deactivated in the catalog for the intraday-India focus).
5. Create, configure, **version**, validate, and get approvals for a strategy
   (SMA crossover, RSI reversion, momentum breakout, or an uploaded Python strategy).
6. **Backtest** (bar replay, Monte Carlo, walk-forward) before deploying a run.
7. Watch live P&L, orders, positions, and trades stream over WebSocket.
8. Track portfolio analytics (Sharpe / Sortino / Calmar), publish to the
   **marketplace**, and ask the **AI assistant** for explanations.
9. Manage risk limits and kill switches, notifications (in-app / email / webhook),
   billing, team, API keys, feature flags, and enterprise security.

## Enterprise capabilities (AlgoMatrics V2)

Twenty phases layered onto the core platform, each with its own operations guide.
All changes are backward-compatible and additive; see [`CHANGELOG.md`](CHANGELOG.md).

| Area | Capability | Guide |
|---|---|---|
| Observability | Prometheus/Grafana/Loki/Alertmanager, RUM, infra sampler | [observability](docs/operations/observability.md) |
| Secrets | Pluggable `env` / AWS Secrets Manager / Fernet-encrypted backends | [secrets](docs/operations/secrets.md) |
| Audit | Immutable SHA-256 hash-chain with append-only trigger | [audit](docs/operations/audit.md) |
| Feature flags | Precedence engine (kill-switch → user → tenant → % rollout) | [feature-flags](docs/operations/feature-flags.md) |
| Rate limiting | Redis sliding-window, scoped + admin overrides | [rate-limiting](docs/operations/rate-limiting.md) |
| Event-driven | `EventBus` abstraction, Streams consumer groups, inbox dedupe | [event-driven](docs/operations/event-driven.md) |
| Workers | Role framework, per-role consumer groups, DLQ | [workers](docs/operations/workers.md) |
| Brokers | Binance (HMAC REST) + Interactive Brokers (Client Portal) | [brokers](docs/operations/brokers.md) |
| Payments | GST/tax breakdown + refunds | [payments](docs/operations/payments.md) |
| Marketplace | Listings, reviews, licenses, revenue split | [marketplace](docs/operations/marketplace.md) |
| Analytics | Sharpe / Sortino / Calmar / drawdown / alpha-beta | [portfolio-analytics](docs/operations/portfolio-analytics.md) |
| Backtesting | Bar-replay engine, Monte Carlo, grid + walk-forward | [backtesting](docs/operations/backtesting.md) |
| AI platform | Claude provider abstraction (assistant, explanations) | [ai](docs/operations/ai.md) |
| Strategy versioning | Semantic versions, diff, validation, approval FSM, deployments | [strategy-versioning](docs/operations/strategy-versioning.md) |
| Notifications | In-app + email + webhook channels, per-user preferences | [notifications](docs/operations/notifications.md) |
| Mobile backend | Device registry, push provider, bootstrap aggregate | [mobile](docs/operations/mobile.md) |
| Enterprise security | OWASP response headers + org IP allowlist | [enterprise-security](docs/operations/enterprise-security.md) |
| High availability | Circuit breaker + hardened readiness probes (503 on degraded) | [high-availability](docs/operations/high-availability.md) |
| Auto scaling | Backlog-driven policy + queue-lag signals + KEDA/HPA | [auto-scaling](docs/operations/auto-scaling.md) |
| Production infra | Startup config self-check, `/health/info`, Kubernetes kit | [production-infrastructure](docs/operations/production-infrastructure.md) |

## Quick start (Docker — one command)

Prerequisites: Docker + Docker Compose.

```bash
cp .env.example .env
docker compose -f deploy/compose/docker-compose.yml up --build
```

This starts PostgreSQL, Redis, the API, worker, trading engine, market-data feed,
scheduler, and the frontend. On first boot a `secrets-init` job generates the JWT
keypair and broker KEK, then a one-shot `migrate` job runs Alembic migrations and
seeds plans, the broker catalog, and a starter instrument universe.

- Frontend: <http://localhost:8080>
- Ops dashboard: <http://localhost:8080/ops> (see
  [docs/operations/ops-dashboard.md](docs/operations/ops-dashboard.md))
- API docs: <http://localhost:8000/docs>
- Health: `GET /api/v1/health/live`, `/health/ready` (503 when degraded),
  `/health/dependencies`, `/health/info` (service/version/build_sha/env)

Register in the UI. Because `EMAIL_BACKEND=console` by default, the verification
link is printed to the API container logs:

```bash
docker compose -f deploy/compose/docker-compose.yml logs -f api | grep email.console_delivery
```

To make yourself a platform admin:

```bash
docker compose -f deploy/compose/docker-compose.yml exec api \
  python scripts/promote_admin.py you@example.com
```

Optional: bring up the observability stack (Prometheus/Grafana/Loki/Alertmanager)
and the scaled worker topology alongside the core compose file:

```bash
docker compose -f deploy/compose/docker-compose.observability.yml up -d
docker compose -f deploy/compose/docker-compose.workers.yml up -d
```

## Local development (without Docker)

Install Python 3.13+, Node 22+, and [`uv`](https://docs.astral.sh/uv/). PostgreSQL
and Redis must be reachable (Compose can provide just those two).

```bash
uv sync --all-groups                     # backend deps
uv run python scripts/generate_dev_secrets.py   # writes ./secrets

# point .env at the generated secrets and local infra, then:
uv run alembic -c backend/alembic.ini upgrade head
uv run python scripts/seed.py

uv run python -m algo_platform.processes.api            # API on :8000
uv run python -m algo_platform.processes.market_data    # simulated feed
uv run python -m algo_platform.processes.trading_engine # paper fills + strategies
uv run python -m algo_platform.processes.worker         # event workers (roles)
uv run python -m algo_platform.processes.scheduler      # billing/hygiene jobs

cd frontend && npm install && npm run dev               # console on :5173
```

Run a single worker role by setting `WORKER_ROLES` (e.g. `WORKER_ROLES='["notification"]'`);
`["all"]` (default) runs every role in one process.

## Quality gates

```bash
make verify          # ruff + mypy + pytest + frontend build + vitest
make test-integration  # PostgreSQL/Redis via testcontainers (needs Docker)
make test-e2e          # paper-trading vertical slice (needs Docker)
```

Every merge keeps the tree **100% Ruff-clean, strict-mypy-clean, and strict-TypeScript**.
CI (`.github/workflows/ci.yml`) runs Ruff, mypy, the unit/architecture/contract
suite, integration + e2e (testcontainers), the frontend build and component tests,
and builds both Docker images.

## Repository layout

```text
backend/     FastAPI control plane, bounded-context modules, runtime processes, migrations
frontend/    React + TS + Tailwind operations console
ops/         Ops dashboard (Raj Quant OS): monitoring frontend (served at /ops) + telemetry backend
packages/    strategy SDK, python SDK, raj_monitor (host telemetry SDK + agent)
agents/      VPS execution agent (MT5)
deploy/
  compose/       core + observability + scaled-workers Docker Compose topologies
  docker/        backend/frontend images + entrypoint
  observability/ Prometheus/Grafana/Loki/Promtail/Alertmanager stack + dashboards
  autoscaling/   KEDA ScaledObjects + API HPA
  k8s/           namespace, config/secrets, migrate Job, deployments, ingress
  nginx/         reverse proxy config
scripts/     seed, dev-secret bootstrap, admin promotion, secrets CLI
tests/       unit, architecture, contract, integration, e2e
docs/        architecture (FOUNDATION + ADRs), development, operations (per-capability guides)
```

Backend bounded contexts under `backend/src/algo_platform/modules/` — `ai`, `audit`,
`billing`, `brokerage`, `feature_flags`, `identity`, `instruments`, `marketplace`,
`mobile`, `notifications`, `organizations`, `portfolio`, `risk`, `strategies`,
`trading` — each follows `domain/ → application/ → infrastructure/ → presentation/`.
Cross-cutting technical concerns live in `shared/` (event bus, circuit breaker,
scaling policy, readiness, rate limiting, secrets, security headers, prometheus).
See [`docs/development/README.md`](docs/development/README.md) for the layering rules.

## Architectural invariants

- Domain code imports no framework, ORM, broker SDK, or transport (enforced by
  `tests/architecture`).
- Cross-context access goes through explicit facades / public `domain.X` contracts.
- Strategies emit intents; they never call a broker directly.
- Every live order passes entitlement, kill-switch, pre-trade risk, and audit gates.
- PostgreSQL is the system of record; Redis is disposable coordination/cache state.
- Tenant identity is explicit in every tenant-owned aggregate, command, and query.
- Broker credentials are envelope-encrypted (AES-256-GCM) and never returned by
  APIs or written to logs; secrets are redacted from structured logs.
- External side effects use a transactional outbox, an event bus, and idempotency keys.
- The API **fails fast** at boot on an unsafe production configuration (insecure
  cookies, wildcard CORS, `env` secrets backend, disabled security headers, …).

## Production deployment

Kubernetes manifests are in [`deploy/k8s/`](deploy/k8s); apply the numbered files
in order (namespace → config/secrets → migrate Job → API → workers → singletons →
ingress), then the autoscalers in [`deploy/autoscaling/`](deploy/autoscaling). The
singleton runtimes (engine, market-data, scheduler) run one replica; the event
workers scale on consumer-group backlog via KEDA. Full sequence and a production
readiness checklist are in
[`docs/operations/production-infrastructure.md`](docs/operations/production-infrastructure.md).

> **Safety note.** Before enabling real live trading, review
> [`docs/COMPLETENESS_AUDIT_2026-07-05.md`](docs/COMPLETENESS_AUDIT_2026-07-05.md)
> and [`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md) — they track
> the remaining critical safety items (strategy execution isolation, simulated-data
> guardrails, engine command durability).
