# Changelog

All notable changes to the Algo Matrics platform are documented here. The format
is loosely based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added — production observability (Master Spec Phase 1)

Enterprise observability delivered end to end, additively and behind
`METRICS_ENABLED`. No database migration or API-contract change; see
`docs/operations/observability.md`.

- **Prometheus metrics foundation** (`shared/infrastructure/prometheus.py`): a
  process-local metric catalogue on an isolated registry covering HTTP,
  trading/orders/P&L, brokers, streams, market data, DB pool, Redis, WebSocket,
  and frontend RUM. API exposes it at the root `/metrics`; background processes
  serve it on `METRICS_PORT` (default 9100).
- **Fixed** the audited defect where request metrics were never recorded — the
  request middleware now resolves the Redis recorder and Prometheus metrics
  lazily from `app.state` and records HTTP count/latency by route template.
- **Correlation IDs**: `X-Correlation-ID` accepted/propagated across services
  and bound into structured logs; the SPA sends a stable per-tab value.
- **Instrumentation** at infrastructure boundaries: outbox worker derives order
  submitted/filled/rejected counters from relayed domain events, market-data and
  engine emit tick metrics, the API samples DB pool + Redis health, and the
  WebSocket hub tracks connections and frames.
- **Observability stack** (`deploy/observability` + compose override):
  Prometheus (with alert rules), Alertmanager (Slack), Loki + Promtail JSON log
  shipping, Grafana with auto-provisioned datasources and three reproducibly
  generated dashboards, plus cAdvisor/node-exporter for container health.
- **Browser RUM**: dependency-free frontend Web Vitals + client-error reporter
  posting to a bounded, allowlisted `/api/v1/rum` intake.
- Tests: 20 new backend unit tests (Prometheus, instrumentation, RUM); ruff +
  strict mypy clean; frontend lint/build/tests green.

### Added — backend test coverage (production-validation Phase 1 & 2)

Increased backend line coverage from **35% → 41%** (10,533 stmts; missed
6,827 → 6,181) and grew the runnable, CI-green suite from **98 → 201 tests**.
All additions run in the default `pytest -m "not integration and not e2e"`
gate — no Docker required.

- **Broker contract tests** (`tests/contract/test_broker_adapters.py`, 36 tests
  — Phase 2): Zerodha, Angel One, Delta, and MT5 adapters exercised end to end
  against recorded-shape fixtures via `httpx.MockTransport` (real request
  building, endpoint/payload shapes, and status/retcode normalization; only the
  socket is substituted). Covers submit/cancel/replace, order-update streaming,
  balances/positions, rejection paths, and MT5 URL security (scheme, HTTPS, and
  host-allowlist enforcement). Paper venue covered via its deterministic
  simulator (reproducible fills, limit-cross, stop-trigger). Adapter coverage
  rose from ~0–29% to 61–85%.
- **Built-in strategy tests** (`tests/unit/test_builtin_strategies.py`, 10
  tests): SMA crossover, RSI reversion, and Donchian breakout candle logic via a
  capturing fake `StrategyContext` with an immediate-fill position model.
  Builtins rose to 90–98%.
- **Domain-layer tests** (47 tests) covering Phase 1 areas without a database:
  - Identity (`test_identity_domain.py`): user lifecycle, MFA, sessions,
    **refresh-token rotation** single-use invariant, one-time e-mail tokens, and
    API-key expiry/revocation.
  - Brokerage (`test_brokerage_domain.py`): credential validation, connection
    verify/fail/disable/rotate, and trading-account onboarding.
  - Risk (`test_risk_domain.py`): limits validation, kill switches, decisions.
  - Organizations + **RBAC** (`test_organizations_domain.py`): org/membership/
    invitation lifecycle and the role→permission mapping (viewer ⊂ trader ⊂
    admin; `TRADING_EXECUTE`/`BILLING_MANAGE` gating).

### Notes — coverage ceiling and remaining work

- The remaining ~4,000 uncovered statements are concentrated in DB/Redis-bound
  code — every `presentation/router.py` (0%), application services
  (billing/strategies/portfolio/trading queries), repositories (~31%), and the
  `processes/*` workers/engine (0%). These are only exercisable through the
  existing testcontainers-Postgres/Redis fixtures, which run **in CI** but not
  in this Docker-less environment. SQLite substitution is not viable because the
  `Base` type map hardwires Postgres `JSONB`/`UUID`. Reaching the 80% target
  requires those integration/router/service suites to run on the CI Docker path.
- Pre-existing (not introduced here): 13 files repo-wide fail
  `ruff format --check`, including 7 production source modules that were not
  touched by this work. All newly added test files are ruff- and
  format-clean.

### Added — frontend workflow completion (Phase 1 / audit Step 3)

- **Watchlists page** (`/app/watchlists`): full create/rename/delete and
  add/remove-instrument workflow wired to the existing `/watchlists` API, with
  live quotes for each instrument via the polling `useQuotes` hook. Adds
  `useCreateWatchlist`, `useRenameWatchlist`, `useDeleteWatchlist`,
  `useAddWatchlistItem`, and `useRemoveWatchlistItem` mutation hooks. Closes the
  audit gap "Watchlist CRUD endpoints and hook exist but no page/component uses
  them."
- **Portfolio page** (`/app/portfolio`): holdings-centric view combining
  `useAccounts`, `usePositions`, and `useExposure` — total equity/cash/exposure
  cards, a holdings table with live marks, allocation by asset class, and a
  per-account balances table. Closes "No dedicated Portfolio page."
- **Notifications history page** (`/app/notifications`): full delivered-alert
  history with All/Unread filtering and per-item / bulk mark-as-read, backed by
  the existing `/notifications` API. Adds `useMarkNotificationRead` and
  `useMarkAllNotificationsRead` hooks and a "View all notifications" link in the
  header bell popover. Closes "No Notifications page/history; only a bell
  popover."
- Sidebar navigation entries and authenticated routes for the three pages.
- Vitest component tests for `WatchlistsPage`, `PortfolioPage`, and
  `NotificationsPage` (frontend suite: 17 tests passing).

### Notes

- No backend, migration, or schema changes were required; all three pages
  consume endpoints that already existed and were previously unconsumed.
- Quality gates after this change: frontend ESLint clean, `tsc -b` + Vite
  production build passing, Vitest 17/17 passing. Backend Ruff, strict mypy, and
  98 unit tests remained green (unchanged).
