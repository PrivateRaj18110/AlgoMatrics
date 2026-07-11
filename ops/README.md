# Raj Quant OS — AlgoMatrics Ops Dashboard

> **Monorepo note.** This app now lives inside the AlgoMatrics platform repo:
> the frontend is served at **`/ops`** by the platform's nginx, the backend
> runs as the `ops-api` compose service, and the `raj_monitor` SDK moved to
> [`packages/raj_monitor`](../packages/raj_monitor). It can also mirror live
> AlgoMatrics platform data via a read-scope API key. Start here:
> [`docs/operations/ops-dashboard.md`](../docs/operations/ops-dashboard.md).
> Paths below are relative to `ops/`.

A production-grade **Trading Operations Center**: a Bloomberg / Grafana / TradingView–inspired
mission control for monitoring trading **strategies**, **machines**, and **trades** across multiple
hosts. Dark-mode, dense, responsive, and built to scale toward institutional-grade monitoring.

This repository is a **monorepo** with a React frontend and a FastAPI backend. The UI ships with a
complete **mock data layer** behind a service abstraction, so it runs end-to-end with **no database
and no backend required** — and can be switched to the live API later without touching components.

---

## Table of contents

1. [Tech stack](#tech-stack)
2. [Folder tree](#folder-tree)
3. [Prerequisites](#prerequisites)
4. [Quick start](#quick-start)
5. [Frontend](#frontend)
6. [Backend](#backend)
7. [Environment variables](#environment-variables)
8. [Mock data & the service layer](#mock-data--the-service-layer)
9. [Installed libraries](#installed-libraries)
10. [Architecture](#architecture)
11. [Deployment](#deployment)
12. [Roadmap](#roadmap)

---

## Tech stack

| Layer        | Technology                                                                                  |
| ------------ | ------------------------------------------------------------------------------------------- |
| **Frontend** | React 19 · Vite 8 · TypeScript · Tailwind CSS v4 · shadcn/ui (Radix) · React Router 7        |
|              | TanStack Query 5 · AG Grid Community · Recharts 3 · Lucide · Framer Motion · react-grid-layout |
| **Backend**  | FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · Uvicorn                                     |
| **Database** | Supabase PostgreSQL *(architected, not yet connected)*                                       |
| **Auth**     | Supabase Auth *(architected, intentionally disabled in v1)*                                  |
| **Deploy**   | Frontend → Vercel · Backend → Docker · Database → Supabase                                   |

---

## Folder tree

```
DTradingDashboard/
├── frontend/                     # React 19 + Vite + TS application
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ui/               # shadcn/ui primitives (button, card, dialog, …)
│   │   │   ├── layout/           # AppLayout, TopBar, Panel, PageHeader
│   │   │   ├── navigation/       # Sidebar, NavItem, nav config
│   │   │   ├── cards/            # MetricCard, MachineCard, StrategyCard
│   │   │   ├── charts/           # Equity, DailyPnL, Performance, Heatmap, …
│   │   │   ├── tables/           # TradesTable (AG Grid), RecentTradesTable
│   │   │   ├── widgets/          # ResourceBar, Sparkline, AlertsPanel, Clock, …
│   │   │   ├── dialogs/          # NotificationsSheet
│   │   │   └── common/           # StatusBadge, PnlValue, QueryState, EmptyState
│   │   ├── pages/                # Dashboard, Strategies, Machines, Trades,
│   │   │                         #   Analytics, Alerts, Settings (+ NotFound)
│   │   ├── hooks/                # TanStack Query hooks + useClock, useConnection…
│   │   ├── services/            # Service layer + mock data fixtures + API client
│   │   │   ├── api/              # client.ts (mock bridge + real fetch)
│   │   │   └── mock/             # deterministic mock fixtures
│   │   ├── providers/            # Query, Theme, Sidebar, Tooltip providers
│   │   ├── types/                # Domain models (Trade, Strategy, Machine, …)
│   │   ├── utils/                # cn, formatters, status helpers, constants
│   │   ├── App.tsx               # Route table (lazy-loaded pages)
│   │   ├── main.tsx              # Entry point
│   │   └── index.css             # Tailwind v4 + design tokens
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig*.json
│   ├── components.json           # shadcn/ui config
│   ├── vercel.json               # SPA rewrites for Vercel
│   └── package.json
│
├── backend/                      # FastAPI service
│   ├── app/
│   │   ├── api/
│   │   │   ├── router.py          # aggregate router
│   │   │   └── routers/health.py  # GET /api/health
│   │   ├── core/config.py         # pydantic-settings configuration
│   │   ├── middleware/cors.py     # CORS setup
│   │   ├── schemas/health.py      # response models
│   │   ├── services/              # business logic (health_service, …)
│   │   ├── database/session.py    # SQLAlchemy session scaffold (inactive)
│   │   ├── models/                # ORM declarative base (ready for models)
│   │   └── utils/
│   ├── tests/test_health.py
│   ├── main.py                    # uvicorn entry point (app = create_app())
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── Dockerfile
│   └── .env.example
│
├── database/                     # reserved for Supabase migrations / schema
├── docs/                         # ARCHITECTURE.md and design notes
├── shared/                       # reserved for shared contracts
└── README.md
```

---

## Prerequisites

- **Node.js ≥ 20** (developed on Node 24) and npm
- **Python ≥ 3.11** (developed on Python 3.12+)
- Git

---

## Quick start

```bash
# 1) Frontend (runs fully on mock data — no backend needed)
cd frontend
npm install
npm run dev          # http://localhost:5173

# 2) Backend (separate terminal)
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload   # http://localhost:8000  (docs at /docs)
```

---

## Frontend

```bash
cd frontend
npm install        # install dependencies
npm run dev        # start Vite dev server  → http://localhost:5173
npm run build      # type-check (tsc -b) + production build → dist/
npm run preview    # preview the production build
npm run typecheck  # type-check only
npm run lint       # ESLint
```

The app is **dark-mode only**, responsive down to tablet / old-iPad Safari, and code-split per route
(each page is its own lazy chunk; AG Grid, Recharts and the router are isolated vendor chunks).

### Pages

| Route          | Description                                                                  |
| -------------- | ---------------------------------------------------------------------------- |
| `/`            | **Dashboard** — system-status strip, 17 KPI cards, a draggable command grid (equity curve, daily PnL, performance, recent trades, alerts), live event terminal, machine + strategy sections |
| `/strategies`  | Reusable strategy cards with status filtering (scales to unlimited strategies) |
| `/trades`      | Professional **AG Grid** blotter with search, sorting, filtering, pagination |
| `/execution`   | Execution monitor — signal→fill pipeline, latency percentiles (P50/P90/P95/P99), throughput, recent order journeys |
| `/risk`        | Risk — daily/weekly/monthly loss limits, exposure by symbol/strategy/broker, margin, drawdown, VaR |
| `/analytics`   | Daily/weekly/monthly PnL, win-rate & profit-factor by strategy, latency, PnL + machine-load heatmaps |
| `/machines`    | Machine health cards (CPU, RAM, disk, temp, internet, broker ping, Python status, uptime, heartbeat) |
| `/brokers`     | Broker connectivity — balance, equity, margin, spread, leverage, open/pending/rejected orders, ping |
| `/accounts`    | Live/prop/demo accounts with equity curves, balances and live pnl          |
| `/events`      | **Event Terminal** — Bloomberg-style live event stream, newest first, severity-coloured, category filter |
| `/logs`        | **Log Viewer** — application / strategy / python / broker / database / system streams with level + search filters |
| `/alerts`      | Alert center with severity filtering and acknowledge actions                 |
| `/settings`    | Settings (general, appearance, data source + refresh interval, notification channels: Telegram/Browser/Email, alert rules, machine/strategy defaults, Supabase auth placeholder) |

All pages communicate through the **service layer** only; the app shell holds a single realtime
subscription (mock engine in mock mode, websocket in live mode) that folds live machine telemetry and
events straight into the TanStack Query cache, so the dashboard updates automatically.

---

## Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
uvicorn main:app --reload         # http://localhost:8000
```

### Endpoints

All endpoints are live and served from in-memory mock repositories. Full reference: [`docs/API.md`](docs/API.md).

| Method | Path                       | Description                                            |
| ------ | -------------------------- | ----------------------------------------------------- |
| GET    | `/`                        | Service info (name, version, links)                   |
| GET    | `/api/health`              | Health probe → `{ status, version, time, environment }` |
| GET    | `/api/dashboard/overview`  | KPI + chart payload                                   |
| GET    | `/api/strategies`          | List strategies (`/{id}` for one)                     |
| GET    | `/api/trades`              | Trade blotter (`?limit=`)                             |
| GET    | `/api/execution/overview`  | Pipeline + latency percentiles                        |
| GET    | `/api/risk/overview`       | Risk posture + exposure breakdowns                    |
| GET    | `/api/analytics`           | Analytics series + heatmaps                           |
| GET    | `/api/machines`            | Machines (`/{id}` for one)                            |
| GET    | `/api/brokers`             | Brokers (`/{id}` for one)                             |
| GET    | `/api/accounts`            | Accounts (`/{id}` for one)                            |
| GET    | `/api/events`              | System event feed (`?limit=`)                         |
| GET    | `/api/logs`                | Logs (`?source=&limit=`)                              |
| GET    | `/api/alerts`              | Alert feed                                            |
| GET/PUT| `/api/settings`            | Read / update application settings                    |
| POST   | `/api/ingest/*`            | **monitor_sdk** ingestion (start, heartbeat, trade, position, metric, event, error) |
| WS     | `/api/ws`                  | Live feed (machine telemetry, events, heartbeats)     |
| —      | `/docs`                    | Interactive Swagger UI                                |

Run the tests:

```bash
pip install -r requirements-dev.txt
pytest -q
```

> The database (Supabase Postgres) and Supabase Auth are **architected but not connected** in v1.

---

## Environment variables

**Frontend** (`frontend/.env.local`, see `.env.example`):

| Variable             | Default | Purpose                                                       |
| -------------------- | ------- | ------------------------------------------------------------- |
| `VITE_API_BASE_URL`  | *(empty)* | Backend API base URL. When empty, the app uses mock data.   |
| `VITE_USE_MOCK`      | `true`  | Force mock mode even when an API URL is set.                  |
| `VITE_APP_VERSION`   | `1.0.0` | Version label shown in the UI.                                |

**Backend** (`backend/.env`, see `.env.example`): `APP_NAME`, `VERSION`, `ENVIRONMENT`, `API_PREFIX`,
`CORS_ORIGINS`, and the (currently blank) `DATABASE_URL` / `SUPABASE_URL` / `SUPABASE_ANON_KEY`.

---

## Mock data & the service layer

The UI never imports mock fixtures directly. Every view goes through **hooks → services → API client**:

```
components → hooks (TanStack Query) → services/*.service.ts → services/api/client.ts
                                                                 ├── USE_MOCK → mock fixtures
                                                                 └── live    → fetch(VITE_API_BASE_URL)
```

To switch the entire app from mock to live data, set `VITE_API_BASE_URL` and `VITE_USE_MOCK=false`.
**No component changes are required** — only the service layer touches the data source.

Mock fixtures are **deterministic** (seeded PRNG) so charts and grids stay stable across renders.

---

## Installed libraries

### Frontend — runtime

`react`, `react-dom`, `react-router-dom`, `@tanstack/react-query`, `ag-grid-community`,
`ag-grid-react`, `recharts`, `lucide-react`, `framer-motion`, `react-grid-layout`,
`class-variance-authority`, `clsx`, `tailwind-merge`, and Radix primitives
(`@radix-ui/react-{slot,dialog,dropdown-menu,label,scroll-area,select,separator,switch,tabs,tooltip}`).

### Frontend — dev

`vite`, `@vitejs/plugin-react`, `typescript`, `typescript-eslint`, `eslint` (+ react-hooks /
react-refresh plugins), `tailwindcss`, `@tailwindcss/vite`, `@types/{react,react-dom,react-grid-layout,node}`,
`globals`.

### Backend

`fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `SQLAlchemy`, `alembic`,
`psycopg[binary]`, `python-dotenv` (+ `pytest`, `httpx`, `ruff` for dev).

---

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full write-up. In brief:

- **Design system in one place.** All colors, radii and typography are CSS variables/tokens in
  `index.css` consumed through Tailwind utilities (`bg-card`, `text-muted-foreground`, …).
- **Composition over duplication.** Reusable primitives (`Panel`, `MetricCard`, `StatusBadge`,
  `QueryState`, `ResourceBar`) are assembled by pages; the same card components power both the
  dashboard and their dedicated pages.
- **Data flow.** TanStack Query owns server state (caching, polling, loading/error states); a thin
  service layer abstracts mock vs. live; React context handles UI state (theme, sidebar).
- **Performance.** Route-level code-splitting, manual vendor chunks, memoized charts/cards, deferred
  search input, and a single Suspense boundary in the layout shell.
- **Backend.** App-factory pattern, layered into routers → services → schemas, with the database and
  middleware isolated so Supabase + feature routers slot in without reshaping the core.

---

## Deployment

- **Frontend → Vercel.** `vercel.json` sets the Vite framework, build command and SPA rewrites.
  Set `VITE_API_BASE_URL` / `VITE_USE_MOCK` in the Vercel project env.
- **Backend → Docker.** `backend/Dockerfile` builds a slim, non-root image:
  ```bash
  cd backend
  docker build -t raj-quant-os-api .
  docker run -p 8000:8000 --env-file .env raj-quant-os-api
  ```
- **Database → Supabase.** Provision a Postgres instance, then set `DATABASE_URL` and run Alembic
  migrations (the SQLAlchemy/Alembic scaffolding is already in place).

---

## Documentation

| Doc | Contents |
| --- | -------- |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System architecture and design principles |
| [`docs/FRONTEND.md`](docs/FRONTEND.md)         | Frontend structure, data flow, realtime, conventions |
| [`docs/BACKEND.md`](docs/BACKEND.md)           | Backend layering, repository pattern, websocket |
| [`docs/API.md`](docs/API.md)                   | Full REST + websocket endpoint reference |
| [`docs/SDK_Integration.md`](docs/SDK_Integration.md) | **How to write `monitor_sdk.py` and add it to the three trading projects** |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)     | Vercel / Docker / Supabase deployment |

---

## Status & remaining work

The platform is **feature-complete**. Every page is built, every endpoint returns data, the websocket
feed is live, and the monitoring infrastructure is delivered as the **Raj Monitor Platform**
([`raj_monitor/`](raj_monitor/README.md)) — a production-grade SDK + Local Agent:

```
Strategy → monitor_sdk → Local Agent → FastAPI (/api/agent/*) → Supabase → Dashboard
```

The agent runs one process per machine, durably queues telemetry (crash/reboot-safe SQLite), collects
host metrics, sends heartbeats, and batch-uploads to the backend with retry + circuit breaking — so
strategies are never blocked and no events are lost. The backend's `/api/agent/*` endpoints fold this
live data into the same repositories + websocket the dashboard already reads, so **no UI redesign was
needed**.

**To go live**, copy `raj_monitor/` into each of the three trading projects (London VPS, Google Cloud,
Personal PC), run an agent per host (see the [Windows](raj_monitor/INSTALL_WINDOWS.md) /
[Linux](raj_monitor/INSTALL_LINUX.md) guides), add `from raj_monitor import monitor`, call
`monitor.start()`, and route execution callbacks through `monitor.trade()` / `monitor.position()` /
`monitor.metric()`. See [`raj_monitor/README.md`](raj_monitor/README.md).

### Future (post-SDK)

- [ ] Connect Supabase Postgres (swap the in-memory repositories for SQLAlchemy)
- [ ] Supabase Auth (login, protected routes, RLS)
- [ ] Persisted dashboard layouts and per-user preferences
- [ ] Per-machine drill-down and historical playback
```
