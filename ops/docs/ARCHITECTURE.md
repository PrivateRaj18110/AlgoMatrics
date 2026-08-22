# Raj Quant OS — Architecture

This document explains how the system is structured and why. It complements the top-level
[`README.md`](../README.md).

## 1. Goals & principles

- **Production architecture, not demo code.** Clear layering, reusable components, typed contracts.
- **Mock-first, API-ready.** The UI is fully functional on bundled mock data and can switch to a live
  backend by changing configuration only — never component code.
- **Dense, professional, dark.** A Bloomberg/Grafana/TradingView aesthetic optimized for desktop,
  laptop and tablet (including old iPad Safari).
- **SOLID & DRY.** Single-responsibility modules, composition over duplication, dependency inversion
  at the data boundary (services depend on an abstraction, not on fixtures or `fetch` directly).

## 2. Frontend layering

```
┌────────────────────────────────────────────────────────────┐
│ pages/*            Route screens (compose components)        │
├────────────────────────────────────────────────────────────┤
│ components/*       ui · layout · cards · charts · tables ·   │
│                    widgets · common  (presentational)        │
├────────────────────────────────────────────────────────────┤
│ hooks/*            TanStack Query wrappers + UI hooks         │
├────────────────────────────────────────────────────────────┤
│ services/*         Domain services (mock ↔ live switch)       │
│   └─ services/api/client.ts   mock bridge + real fetch        │
├────────────────────────────────────────────────────────────┤
│ types/*            Domain models (single source of truth)     │
│ utils/*            cn, formatters, status, constants          │
└────────────────────────────────────────────────────────────┘
```

**Why this split:**

- **Components** are dumb and reusable. `MetricCard`, `MachineCard`, `StrategyCard`, `Panel`,
  `StatusBadge`, `PnlValue` and `QueryState` are used by multiple pages. The dashboard reuses the same
  machine/strategy cards as the dedicated pages — no copy/paste.
- **Hooks** isolate server-state concerns (caching, polling, `isPending`/`isError`). Pages render
  `QueryState` to get uniform loading/error/empty handling everywhere.
- **Services** are the only modules that know whether data comes from mock fixtures or a live API.
  Each service method branches on `USE_MOCK` and returns the same typed shape either way.

## 3. State management

| Concern         | Owner                              | Notes                                            |
| --------------- | ---------------------------------- | ------------------------------------------------ |
| Server state    | **TanStack Query**                 | caching, polling, retries; live updates folded in via `useRealtime` |
| Realtime feed   | `services/realtime` + `useRealtime`| mock engine (in-browser) ↔ websocket; updates the Query cache |
| Settings        | `SettingsProvider` (React context) | refresh interval + notification prefs, persisted (localStorage ↔ `/api/settings`) |
| Theme           | `ThemeProvider` (React context)    | dark default, light fallback, persisted          |
| Sidebar         | `SidebarProvider` (React context)  | collapse (desktop) + drawer (mobile), persisted  |
| Ephemeral UI    | local `useState`                   | filters, search, acknowledged alerts             |

**Realtime.** A single `useRealtime()` subscription in `AppLayout` connects to the active transport
(`services/realtime/socket.ts`) — the in-browser **mock engine** in mock mode, a reconnecting
**websocket** (`/api/ws`) in live mode — and folds `machines`/`event` messages straight into the Query
cache. Both transports speak one typed protocol, so pages update automatically in either mode. Refresh
cadence for polled queries is driven by the user's chosen interval via `useRefetchInterval()`.

## 4. Design system

All visual tokens live in `src/index.css` as Tailwind v4 `@theme` variables — surfaces
(`--color-background`, `--color-card`), semantics (`--color-success/warning/danger`), brand
(`--color-primary`), borders, chart series, radii and fonts. Components consume them through utilities
(`bg-card`, `text-muted-foreground`, `border-border`), so the entire palette is retunable in one file.

shadcn/ui primitives (Radix under the hood) live in `components/ui`. AG Grid is themed via the Theming
API (`themeQuartz.withParams`) using the same hex values, so the data grid matches the rest of the UI.

## 5. Performance

- **Route-level code splitting** via `React.lazy` — each page is its own chunk.
- **Manual vendor chunks** (`vite.config.ts`) keep AG Grid (~1 MB) and Recharts out of the initial
  bundle; the dashboard paints before the grid loads.
- **Memoization** of charts and cards (`React.memo`), `useMemo` for derived aggregates.
- **Deferred input** (`useDeferredValue`) on the trade blotter search to keep typing smooth.
- **Single Suspense boundary** in `AppLayout` with a skeleton fallback.

## 6. Backend layering

```
main.py (create_app + lifespan)
  → middleware/cors.py
  → api/router.py (aggregate: 15 routers)
      → api/routers/<domain>.py        thin, typed (response_model)
          → services/*  (where logic exists: health, settings, ingest)
          → repositories/*  (repository pattern over mock_data fixtures)
              → schemas/*  (Pydantic v2, mirror frontend types/)
  → realtime/broadcaster.py + publisher.py   websocket fan-out + mock event loop
core/config.py        pydantic-settings (single source of config)
database/session.py   SQLAlchemy session factory (lazy, inactive until DATABASE_URL set)
```

The **app-factory pattern** (`create_app()`) makes the service trivially testable (`TestClient(app)`).
The **repository pattern** (`repositories/base.InMemoryRepository`) is the data-access seam: every
router/service depends on the repository interface, not on fixtures or SQL. The **lifespan** starts a
background publisher that streams mock telemetry + events over the websocket. The **ingest** endpoints
(`/api/ingest/*`) implement the `monitor_sdk` contract — strategy calls become events/logs and are
broadcast live.

## 7. Extending to live data

1. Provision Supabase, set `DATABASE_URL`, create models + Alembic migrations.
2. Re-implement `app/repositories/*` against SQLAlchemy — routers, services and schemas are untouched.
3. On the frontend, set `VITE_API_BASE_URL` and `VITE_USE_MOCK=false`.

Because the contract (`types/` ↔ `schemas/`) and both the service and repository interfaces stay
identical, the swap is configuration + one layer — not a rewrite. The only net-new code for a fully
live system is `monitor_sdk.py` in the three trading projects (see
[`SDK_Integration.md`](SDK_Integration.md)).
