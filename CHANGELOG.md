# Changelog

All notable changes to the Algo Matrics platform are documented here. The format
is loosely based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added — enterprise rate limiting (Master Spec Phase 5)

Redis-backed sliding-window rate limiting across six scopes with burst control
and runtime admin overrides, replacing fixed windows. Additive; no schema or
API-contract change. See `docs/operations/rate-limiting.md`.

- **Sliding window** (`shared/infrastructure/rate_limiting`): a sorted-set log
  (`RedisGateway.sliding_window_hit`, one pipeline per check); `RateLimitRule`
  supports an optional short burst window; decision logic is pure and unit
  tested via an in-memory store.
- **Scopes**: tenant, user, api_key, ip, broker, route — a request is denied if
  any applies. Global per-IP `RateLimitMiddleware` (429 + Retry-After +
  X-RateLimit-* headers, health/metrics exempt, fail-open); `rate_limit()` route
  dependency refactored onto the sliding window (same signature); new
  `scoped_rate_limit()` dependency for multi-scope route limits.
- **Admin overrides** (`/admin/rate-limits`): retune a named limit or bypass a
  `{scope, subject}` at runtime; each change is audited.
- Settings: RATE_LIMIT_ENABLED, IP_RATE_LIMIT_PER_MINUTE,
  IP_RATE_LIMIT_BURST_PER_SECOND.
- 16 new unit tests (limiter, middleware, scopes, overrides); ruff + strict mypy
  clean; 223 backend unit/arch tests pass.

### Added — enterprise feature flags (Master Spec Phase 4)

Runtime-configurable feature flags with no deployment required. New
`feature_flags` module (Clean Architecture). See `docs/operations/feature-flags.md`.

- **Evaluation** (`domain/flags.py`, pure/unit-tested): precedence kill-switch >
  user > tenant > environment override > deterministic percentage rollout >
  default. Scopes: environment, tenant, user.
- **Storage/service**: `feature_flags` + `feature_flag_overrides` tables
  (migration 0007, seeds marketplace/ai/paper_trading/live_trading and per-broker
  gates); service with a short-TTL Redis snapshot cache invalidated on write.
- **API**: `GET /feature-flags` evaluates all flags for the caller; admin
  `/admin/feature-flags` CRUD for flags and scoped overrides (each mutation
  audited); `require_feature(key)` dependency to gate routes.
- **Frontend**: `useFeatureFlags`/`useFeatureEnabled` hooks and a `<Feature>`
  gate; Admin → Feature Flags management UI (toggle enabled/kill switch, rollout).
- 11 evaluation unit tests; ruff + strict mypy clean; 208 backend and 17 frontend
  tests pass.

### Added — immutable audit platform (Master Spec Phase 3)

Turns the existing append-only audit trail into a tamper-evident, verifiable
immutable log without changing its consumers. See `docs/operations/audit.md`.

- **Hash chain** (`modules/audit/application/hashing.py`): each entry links to the
  previous via SHA-256 (`prev_hash` → `entry_hash`); `verify_chain` pinpoints the
  first tampered/broken/deleted entry. Pure and reused by the migration backfill.
- **Immutable at the DB**: migration `0006` adds `correlation_id`, `session_id`,
  `sequence`, `prev_hash`, `entry_hash` (baseline-compatible `ADD COLUMN IF NOT
  EXISTS`), backfills the chain over existing rows, and installs a trigger that
  makes `UPDATE`/`DELETE` on `audit_log` raise.
- **Chained writes**: `AuditService.record` appends under a
  `pg_advisory_xact_lock`; new correlation/session parameters are optional so
  every existing caller is unchanged. `verify_integrity()` recomputes the chain.
- **API**: audit search filters by correlation id, resource type, and date range
  and returns the chain fields; new admin `GET /audit-events/integrity`.
- **UI**: `/app/audit` gains resource/correlation filters, an expandable
  before/after diff, and the entry hash.
- 6 pure hashing/verification unit tests + updated frontend test; ruff + strict
  mypy clean; 198 backend unit/arch tests and 17 frontend tests pass. DB-level
  trigger/chain behaviour is covered by Docker-gated integration tests.

### Added — secrets management (Master Spec Phase 2)

Pluggable secrets management with a safe `.env` fallback and log redaction. Fully
additive; `SECRETS_BACKEND=env` (default) preserves prior behaviour exactly. No
database migration or API-contract change. See `docs/operations/secrets.md`.

- **Provider abstraction** (`shared/infrastructure/secrets`): a `SecretsResolver`
  layers a backend over the existing settings loaders — a missing or failed
  managed secret always falls back to `.env`, so enabling a backend cannot
  regress a working deployment. JWT keys, broker KEK, and payment secrets are
  resolved through it in the API app and trading engine.
- **Backends**: `env` (optional `ALGO_SECRET_<NAME>` overrides), `aws` (AWS
  Secrets Manager, lazy boto3 `aws` extra, TTL cache that picks up rotation on
  expiry with stale-cache-on-outage resilience), and `encrypted` (Fernet
  document for local development with a `secrets_cli` keygen/encrypt/decrypt CLI).
- **Never expose secrets to logs**: a structlog processor masks secret-looking
  keys (password/secret/token/authorization/api_key/private_key/kek/credential/
  passphrase) including nested structures.
- `.gitignore` blocks plaintext secret documents and key files.
- 22 new unit tests; ruff + strict mypy clean; 192 unit/arch tests pass.

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
