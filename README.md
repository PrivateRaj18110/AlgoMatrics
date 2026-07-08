# Algo Matrics Platform

A production-grade, multi-tenant algorithmic trading platform: strategies,
brokers, risk controls, SaaS billing, and real-time P&L in one console.

The repository is a monorepo built on **Clean Architecture** and **Domain-Driven
Design** as a modular monolith plus specialized runtimes:

- a **FastAPI control plane** (`/api/v1`) with JWT auth, RBAC, and RFC 9457 errors;
- independently runnable **trading engine**, **market-data**, **worker (outbox)**,
  and **scheduler** processes;
- a broker-neutral **strategy SDK** with sandboxed uploads and first-party strategies;
- a **React + TypeScript operations console** (Vite, Tailwind 4, TanStack Query);
- **Docker Compose** deployment that brings the whole stack up with one command.

The canonical design is in [`docs/architecture/FOUNDATION.md`](docs/architecture/FOUNDATION.md).

## What a new user can do

1. Register an account and verify their e-mail.
2. Log in securely (with optional TOTP MFA).
3. Subscribe to a plan (Free / Starter / Pro / Enterprise) via Razorpay or Stripe.
4. Connect a broker — start with the built-in **Paper Trading** simulator.
5. Create and configure a strategy (SMA crossover, RSI reversion, momentum breakout,
   or an uploaded Python strategy).
6. Deploy a strategy run and start paper trading.
7. Watch live P&L, orders, positions, and trades stream over WebSocket.
8. Manage risk limits and kill switches, billing, team, API keys, and security.

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
- API docs: <http://localhost:8000/docs>

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
uv run python -m algo_platform.processes.worker         # outbox relay
uv run python -m algo_platform.processes.scheduler      # billing/hygiene jobs

cd frontend && npm install && npm run dev               # console on :5173
```

## Quality gates

```bash
make verify          # ruff + mypy + pytest + frontend build + vitest
make test-integration  # PostgreSQL/Redis via testcontainers (needs Docker)
make test-e2e          # paper-trading vertical slice (needs Docker)
```

CI (`.github/workflows/ci.yml`) runs Ruff, mypy, the unit/architecture/contract
suite, integration + e2e (testcontainers), the frontend build and component tests,
and builds both Docker images.

## Repository layout

```text
backend/     FastAPI control plane, bounded-context modules, runtime processes, migrations
frontend/    React + TS + Tailwind operations console
packages/    strategy SDK, python SDK
agents/      VPS execution agent (MT5)
deploy/      Docker images, Compose topology, nginx
scripts/     seed, dev-secret bootstrap, admin promotion
tests/       unit, architecture, contract, integration, e2e
docs/        architecture, operations
```

Each bounded context follows `domain/ → application/ → infrastructure/ → presentation/`.
See [`docs/development/README.md`](docs/development/README.md) for the layering rules.

## Architectural invariants

- Domain code imports no framework, ORM, broker SDK, or transport (enforced by
  `tests/architecture`).
- Strategies emit intents; they never call a broker directly.
- Every live order passes entitlement, kill-switch, pre-trade risk, and audit gates.
- PostgreSQL is the system of record; Redis is disposable coordination/cache state.
- Tenant identity is explicit in every tenant-owned aggregate, command, and query.
- Broker credentials are envelope-encrypted (AES-256-GCM) and never returned by
  APIs or written to logs.
- External side effects use a transactional outbox and idempotency keys.
