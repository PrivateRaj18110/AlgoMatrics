# Frontend

React 19 + Vite + TypeScript + Tailwind v4. Dark-first Bloomberg/Grafana-style terminal, responsive to
tablet/mobile, code-split per route.

## Data flow (strict layering)

```
components → hooks (TanStack Query) → services/*.service.ts → services/api/client.ts
                                                               ├── USE_MOCK → mock fixtures
                                                               └── live    → fetch(VITE_API_BASE_URL)
```

Components **never** fetch directly and never import mock fixtures — they call hooks, which call
services. Flip `VITE_API_BASE_URL` + `VITE_USE_MOCK=false` to move the whole app to the live backend
with zero component changes.

## Realtime

`services/realtime/` provides a transport with two implementations behind one interface
(`RealtimeTransport.connect`):

- **`engine.ts`** — in-browser mock engine. Reference-counted interval that jitters machine telemetry,
  emits events and a connection heartbeat. Runs only while subscribed.
- **`socket.ts`** — reconnecting websocket (`/api/ws`) used in live mode.

`hooks/useRealtime.ts` is mounted **once** in `AppLayout` and folds incoming `machines`/`event`
messages straight into the Query cache, so any page reading `useMachines`/`useEvents` updates live.

## Settings

`providers/SettingsProvider` loads persisted `AppSettings` (localStorage in mock mode, `/api/settings`
in live mode) and exposes `useSettings()` + `useRefetchInterval()`. Every data hook derives its
auto-refresh cadence from the user's chosen refresh interval.

## Structure

```
src/
├── components/
│   ├── ui/          # shadcn/ui primitives
│   ├── layout/      # AppLayout, TopBar, Panel, PageHeader
│   ├── navigation/  # Sidebar (grouped sections), NavItem, navConfig
│   ├── cards/       # Metric/Machine/Strategy/Broker/Account cards
│   ├── charts/      # Equity, DailyPnL, Performance, Category, Pnl, Heatmap…
│   ├── tables/      # TradesTable (AG Grid)
│   ├── widgets/     # EventTerminal, LogViewer, ExecutionPipeline,
│   │                #   SystemStatusBar, ResourceBar, Sparkline…
│   └── common/      # StatusBadge, PnlValue, QueryState, EmptyState
├── pages/           # 12 pages + Events terminal + NotFound
├── hooks/           # one Query hook per domain + useRealtime
├── services/        # service layer, mock fixtures, realtime, api client
├── providers/       # Query, Theme, Settings, Sidebar, Tooltip
├── types/           # domain models (one file per domain)
└── utils/           # cn, formatters, status helpers, constants
```

## Pages

Dashboard · Strategies · Trades · Execution · Risk · Analytics · Machines · Brokers · Accounts ·
Events (terminal) · Logs · Alerts · Settings. Routes are lazy-loaded (`App.tsx`); the sidebar
(`navConfig.ts`) is the single source of truth for navigation, grouped into Overview / Trading /
Infrastructure / Operations.

## Conventions

- **Design tokens** live once in `index.css` (`@theme`) and are consumed via Tailwind utilities
  (`bg-card`, `text-muted-foreground`, `text-success`…). No hard-coded colours in components.
- **Numbers** use the `.tabular` class (mono + tabular figures); format via `utils/format.ts`.
- **Loading/error/empty** states go through `QueryState` + `Skeleton`/`EmptyState`/`ErrorState`.
- **Memoize** charts/cards (`memo`) and derive summaries with `useMemo`.

## Commands

```bash
npm run dev        # Vite dev server → http://localhost:5173
npm run build      # tsc -b + vite build → dist/
npm run typecheck  # types only
npm run lint       # ESLint
npm run preview    # preview production build
```

## Performance

Route-level code-splitting (each page is its own chunk), isolated vendor chunks (AG Grid, Recharts,
router), memoized presentational components, deferred search inputs (`useDeferredValue`), virtualized
grid (AG Grid), and a single Suspense boundary in the shell.
