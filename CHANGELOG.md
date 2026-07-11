# Changelog

All notable changes to the Algo Matrics platform are documented here. The format
is loosely based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added — Ops dashboard integration + intraday-India refocus

- **Ops dashboard** (`ops/`, served at `/ops`): the Raj Quant OS monitoring
  monorepo integrated as a separate app — React 19 frontend (subpath build),
  FastAPI telemetry backend (`/ops/api/agent/*` ingest, websocket), and the
  `raj-monitor` SDK/agent at `packages/raj_monitor`. The ops backend mirrors
  live platform data via an org-scoped read API key with mock fallback.
  Compose service `ops-api`, nginx `/ops` locations, CI jobs, docs:
  `docs/operations/ops-dashboard.md`.
- **Flattrade broker** (`flattrade`): Noren REST execution adapter +
  connection verifier + catalog entry (intraday product default). 6 new
  contract tests.
- **Indian market info**: `GET /market-info/indices` + `/market-info/quotes`
  (free Yahoo Finance chart API, 60 s cache, NSE/BSE only) + console
  **Market** page. 4 new contract tests.
- **Console**: orders/positions/trades/portfolio/risk consolidated into one
  tabbed **Trading** page (`/app/trading/:tab`, old paths redirect);
  Backtesting page unrouted for now (`/app/backtesting` → strategies).
- **Broker catalog**: Delta, MT5, Binance, Interactive Brokers deactivated by
  the seed (adapters retained); Flattrade added.
- `scripts/send_test_email.py` + `docs/operations/go-live-checklist.md`
  (Search Console verification, SMTP/SPF/DKIM steps).

### Added — Production infrastructure (Master Spec Phase 20)

Kubernetes deployment kit + runtime guardrails. See
`docs/operations/production-infrastructure.md`.

- **Startup self-check** (`shared/application/production_readiness.py`, pure):
  `create_app` refuses to boot in production on unsafe config (insecure cookies,
  CORS `*`/plain-http, security headers/rate limiting off, `env` secrets backend,
  http app_base_url); warnings elsewhere. Fail-fast, 12-Factor.
- **Release identity**: `GET /health/info` (service/version/build_sha/env);
  `APP_VERSION` + `BUILD_SHA` settings; OpenAPI version derives from `APP_VERSION`.
- **Manifests** (`deploy/k8s/`): namespace, config/secret template, migrate Job,
  API Deployment+Service (health probes), KEDA-scaled worker Deployments,
  singleton engine/market-data/scheduler (`Recreate`, replicas=1), TLS ingress.
- Settings: `APP_VERSION`, `BUILD_SHA`.
- 7 new unit tests; ruff + strict mypy clean; 386 backend tests pass. No
  migration; no user-facing frontend (ops).

### Added — Auto scaling (Master Spec Phase 19)

Backlog-driven horizontal scaling for the event workers + CPU-based HPA for the
API. See `docs/operations/auto-scaling.md`.

- **Scaling policy** (`shared/application/scaling.py`, pure): `desired_replicas`
  (ceil(backlog/target), clamped) + `recommend` (up/down/hold).
- **Signals**: Redis gateway `xlen` + `consumer_group_lag` (XINFO GROUPS lag →
  pending fallback); `ScalingReporter`; admin `GET /admin/scaling` (stream depth
  + per-`worker:<role>` backlog and recommendation); infra sampler now publishes
  the `stream_depth` gauge for the event stream.
- **Manifests**: `deploy/autoscaling/keda-scaledobjects.yaml` (KEDA redis-streams
  scaler per worker) + `hpa-api.yaml` (API CPU HPA).
- Settings: `SCALING_EVENT_STREAM`, `SCALING_CONSUMER_GROUPS`,
  `SCALING_TARGET_BACKLOG_PER_REPLICA`, `SCALING_MIN_REPLICAS`,
  `SCALING_MAX_REPLICAS`.
- 11 new unit tests; ruff + strict mypy clean; 379 backend tests pass. No
  migration; no user-facing frontend (ops).

### Added — High availability (Master Spec Phase 18)

Hardened health probes and a reusable circuit breaker. See
`docs/operations/high-availability.md`.

- **Circuit breaker** (`shared/application/circuit_breaker.py`, pure, clock-
  injectable): closed → open → half-open state machine; `call()` short-circuits
  with `CircuitOpenError` while open. Wired around the notification webhook
  channel. Config `CIRCUIT_BREAKER_FAILURE_THRESHOLD` / `_RESET_SECONDS`.
- **Readiness** (`shared/application/readiness.py`, pure): `overall_status` with
  a critical-vs-optional distinction.
- **`/health/ready`** now bounds each dependency probe by
  `READINESS_TIMEOUT_SECONDS` and returns **503 when degraded** so a sick replica
  is pulled from rotation; `/health/dependencies` stays 200 (introspection).
- Settings: `READINESS_TIMEOUT_SECONDS`, `CIRCUIT_BREAKER_FAILURE_THRESHOLD`,
  `CIRCUIT_BREAKER_RESET_SECONDS`.
- 15 new unit tests; ruff + strict mypy clean; 368 backend tests pass. No
  migration; no user-facing frontend (ops endpoints).

### Added — Enterprise security (Master Spec Phase 17)

OWASP response headers on every response + a per-organization IP allowlist. See
`docs/operations/enterprise-security.md`.

- **Security headers** (`shared/infrastructure/security_headers.py`, pure +
  `SecurityHeadersMiddleware`): nosniff, `X-Frame-Options: DENY`, Referrer-Policy,
  COOP/CORP, Permissions-Policy, CSP (relaxed for dev docs); HSTS only in
  staging/production. Outermost layer, `SECURITY_HEADERS_ENABLED` (default true),
  fills gaps without clobbering handler-set headers.
- **Org IP allowlist** (`organizations/domain/ip_allowlist.py`, pure; stored in
  `settings` JSON — no new table): validate/normalize IPv4+IPv6 addresses & CIDR;
  empty = allow-all, fail-closed on unparseable IP when configured. Enforced in
  the tenant dependency (→ 403). Admin `GET`/`PUT
  /organizations/current/ip-allowlist` (owner/admin, audited).
- **Frontend**: Settings → Organization "IP allowlist" card.
- Settings: `SECURITY_HEADERS_ENABLED`.
- 16 new unit tests (incl. middleware integration); ruff + strict mypy clean;
  353 backend + 17 frontend tests pass.

### Added — Mobile backend (Master Spec Phase 16)

A `modules/mobile` bounded context: device registry, push provider abstraction,
and a bootstrap aggregate. See `docs/operations/mobile.md`.

- **Device registry** (`mobile_devices` table, migration `0014`): register
  (idempotent by push token), list, unregister — tenant + owner scoped. Push
  tokens validated on write.
- **Push** (`PushProvider` port + `NullPushProvider` default, `PUSH_PROVIDER`
  setting): `DeviceService.push_to_user` fans a display-clamped `PushMessage` to
  a user's devices and prunes provider-reported invalid tokens. Wired via
  `app.state.push_provider` / `PushProviderDep`.
- **Bootstrap** `GET /mobile/bootstrap`: profile + unread badge + evaluated
  feature flags + device count in one cold-start round-trip.
- **Frontend**: Settings → Security "Registered devices" card (list + unregister).
- Settings: `PUSH_PROVIDER` / `FCM_CREDENTIALS_JSON`.
- 10 new domain unit tests; ruff + strict mypy clean; 337 backend + 17 frontend
  tests pass; architecture import rules green.

### Added — Multi-channel notifications (Master Spec Phase 15)

Email + outbound webhook delivery driven by per-recipient preferences, on top of
the existing in-app + WebSocket path. See `docs/operations/notifications.md`.

- **Routing** (`notifications/domain/delivery.py`, pure): `resolve_channels`
  with a severity threshold and quiet-hours window (past-midnight wrap
  supported); in-app is always on, email/webhook opt-in, `critical` can bypass
  quiet hours.
- **Channels** (`infrastructure/channels.py`): email + webhook adapters and a
  `NotificationDispatcher` (failures logged, never propagated). Webhook targets
  pass an SSRF guard (HTTPS only; loopback/private/reserved hosts rejected).
  `NotificationService.notify(..., delivery=...)` opts into external fan-out —
  default behaviour unchanged.
- **Preferences** (`notification_preferences` table, migration `0013`):
  `GET`/`PUT /notifications/preferences`, tenant-scoped; webhook URL revalidated
  on write.
- **Frontend**: Settings → Notifications "Delivery channels" card (toggles,
  webhook URL, min severity, quiet hours).
- 11 new domain unit tests; ruff + strict mypy clean; 327 backend + 17 frontend
  tests pass.

### Added — Strategy versioning (Master Spec Phase 14)

Semantic versioning, diff, validation, an approval workflow, and deployment
history over the existing immutable `StrategyVersion` records. See
`docs/operations/strategy-versioning.md`.

- **Domain** (`strategies/domain/versioning.py`, pure): `SemanticVersion`
  (parse/compare/bump), `diff_versions` with `suggested_bump`,
  `validate_manifest`, and an approval state machine (`draft → pending_review →
  approved/rejected`, illegal transitions raise).
- **Service/API**: approval workflow endpoints
  (`/strategy-versions/{id}/{submit,approve,reject,withdraw}`), `/validate`,
  `/diff`, `/strategies/{id}/deploy`, `/strategies/{id}/deployments` — permission-
  gated (STRATEGIES_VIEW/MANAGE) and tenant-scoped. Approval syncs the version's
  `approved_for_live` flag.
- **Migration** `0012`: `strategy_version_approvals` + `strategy_deployments`
  (additive; baseline exclusion pinned).
- 13 new domain unit tests; ruff + strict mypy clean; 316 backend tests pass.
  Versioning UI on the strategy detail page is a scoped follow-up.

### Added — AI platform (Master Spec Phase 13)

A trading assistant plus domain explanations built on Claude behind a pluggable
provider, gated by the `ai` feature flag. See `docs/operations/ai.md`.

- **Provider abstraction** (`modules/ai`): `LLMProvider` port; `AnthropicProvider`
  (official async SDK, `claude-opus-4-8`, adaptive thinking, lazy `ai` extra) and
  a default `NullProvider` that never calls out (safe + hermetic tests).
- **Prompts** (`domain/prompts.py`, pure): domain-scoped, no-fabrication builders
  for the assistant, strategy/risk explanation, log analysis, NL analytics, and
  broker diagnostics.
- **API** (`/ai`, `require_feature('ai')`): assistant, explain-strategy,
  explain-risk, analyze-logs, analytics, broker-diagnostics, prompt-templates —
  each takes the domain object the caller already holds.
- **Frontend**: `/app/assistant` chat page; nav entry shown only when the flag is on.
- Settings: AI_PROVIDER / ANTHROPIC_API_KEY / AI_MODEL / AI_MAX_TOKENS.
- 17 new unit tests (prompts, null provider offline, factory, service); ruff +
  strict mypy clean; 306 backend + 17 frontend tests pass.

### Added — backtesting engine (Master Spec Phase 12)

A deterministic backtesting engine with Monte Carlo, optimization, and
walk-forward, scored with the shared portfolio metrics. See
`docs/operations/backtesting.md`.

- **Engine** (`strategies/domain/backtest.py`, pure): bar replay with
  fees/slippage → equity curve, trades, Sharpe/Sortino/Calmar/drawdown;
  seeded `monte_carlo`; `grid_search` optimization; `walk_forward` evaluation.
- **Signal registry**: pure bar-based builders for sma_crossover / rsi_reversion
  / breakout.
- **Service + API**: run/monte-carlo/optimize/list/get under `/backtests`
  (permission-gated); runs persisted to `backtest_runs` (migration 0011).
- **Frontend**: `/app/backtesting` runs a backtest over an editable price series
  and shows the metric tiles.
- 15 new unit tests (engine + signals); ruff + strict mypy clean; 293 backend +
  17 frontend tests pass.

### Added — portfolio analytics (Master Spec Phase 11)

Risk-adjusted performance metrics on top of the existing dashboard/equity/
drawdown/exposure/allocation views. See `docs/operations/portfolio-analytics.md`.

- **Metrics library** (`portfolio/domain/metrics.py`, pure/unit-tested): Sharpe,
  Sortino, Calmar, max drawdown, annualized return, volatility, alpha/beta
  (CAPM), returns_from_equity — defensive on short/degenerate inputs.
- **Integration**: `performance_summary` computes Sharpe/Sortino/Calmar and
  annualized return from the equity curve's periodic returns; the API
  `PerformanceSummaryResponse` and the Analytics page expose them.
- Alpha/beta are implemented and await a benchmark feed to be surfaced.
- 12 metric unit tests; ruff + strict mypy clean; 278 backend + 17 frontend tests.

### Added — strategy marketplace (Master Spec Phase 10)

A store to publish, license, and review strategies, gated by the `marketplace`
feature flag. New `modules/marketplace` (Clean Architecture). See
`docs/operations/marketplace.md`.

- **Domain**: Listing (pricing/revenue share, draft→published→unlisted), Review
  (license-gated, one per org), License (grant/active/expiry/revoke), pure
  `revenue_split`.
- **Storage/service**: three tables (migration 0010) + repository; service for
  publish, browse-with-stats, detail, acquire license, review, my licenses, and
  per-currency revenue reporting.
- **API** (`/marketplace`, `require_feature('marketplace')`): publish
  (ownership-checked via a new `StrategyDirectory` read facade), browse, detail,
  reviews, license, unlist, licenses, revenue.
- **Frontend**: `/app/marketplace` browse+license page; nav entry shown only when
  the flag is enabled (feature-driven nav filtering).
- 10 domain unit tests; ruff + strict mypy clean; 266 backend + 17 frontend tests.

### Added — payments: tax & refunds (Master Spec Phase 9)

Completed the billing surface with GST/tax on invoices and a provider refund
flow (Stripe/Razorpay), on top of the existing subscriptions, coupons, trials,
usage metering, and webhooks. See `docs/operations/payments.md`.

- **Tax (GST)**: pure `domain/tax.py` (compute_tax + CGST/SGST/IGST breakdown);
  `Invoice` gains `tax`/`tax_rate` and taxes the post-discount amount into the
  total; migration 0008; `GST_RATE_PERCENT` (18% default) applied to INR
  invoices at checkout and renewal.
- **Refunds**: `PaymentProvider.refund_payment` + Stripe/Razorpay impls;
  `Payment.refunded_amount` + `refund()` (full/partial, CAPTURED→REFUNDED,
  balance-guarded); migration 0009; `SubscriptionService.refund_payment`; admin
  `POST /admin/payments/{id}/refund` (audited).
- 12 new unit tests (tax rounding/breakdown/invoice totals, refund invariants);
  ruff + strict mypy clean; 313 unit/arch/contract tests pass.

### Added — broker integrations (Master Spec Phase 8)

Binance and Interactive Brokers join the shared broker abstraction, completing
the spec's venue set (Angel, Zerodha, Delta, Binance, IBKR, Paper, MT5). See
`docs/operations/brokers.md`.

- **BinanceExecutionAdapter**: HMAC-signed Spot REST (submit/cancel/cancelReplace,
  openOrders polling with status normalization, balances).
- **IbkrExecutionAdapter**: Client Portal gateway REST with the reply-confirmation
  order flow, modify, live-order polling, ledger balances/positions; user-supplied
  gateway URL restricted to HTTPS-or-loopback (SSRF guard).
- `BrokerCode.BINANCE` / `INTERACTIVE_BROKERS`, `LiveRouter` wiring, and seeded
  catalog entries with their credential schemas.
- 11 new contract tests via `httpx.MockTransport`; ruff + strict mypy clean; 301
  unit/arch/contract tests pass.

### Added — worker separation (Master Spec Phase 7)

The single worker becomes a set of independently deployable roles hosted by one
thin, supervised process. See `docs/operations/workers.md`.

- **Framework**: WorkerContext + WorkerRole contract, a runner that supervises
  roles (restart-on-crash with backoff, graceful stop), and a registry selected
  by `WORKER_ROLES` (default `["all"]`).
- **Behaviour-preserving split**: the outbox relay and e-mail delivery are
  extracted into `OutboxRelayWorker` / `EmailWorker`.
- **Domain workers**: notification, analytics, audit, report, billing,
  settlement, and trading each consume the `events` stream via their own
  consumer group (Phase 6 StreamConsumer) with inbox dedupe and event-type
  prefix routing. analytics aggregates per-day counters; notification fans events
  out to organization notifications; the rest are observable per-domain seams.
- **Orchestration**: `docker-compose.workers.yml` narrows the base worker to
  relay+email and runs each domain consumer as its own scalable service.
- 17 new unit tests (supervision, restart, role selection, prefix routing,
  analytics counters); ruff + strict mypy clean; 245 backend unit/arch tests pass.

### Added — event-driven architecture (Master Spec Phase 6)

A transport-agnostic event bus so the messaging backend (Redis Streams today;
Kafka/NATS/RabbitMQ later) is pluggable with no business-logic rewrite. See
`docs/operations/event-driven.md`.

- **Ports** (`shared/application/event_bus.py`): EventPublisher / EventConsumer /
  EventBus with consumer-group semantics (at-least-once, ack, stale reclaim, DLQ).
- **Redis backend** (`RedisStreamsEventBus`) + typed gateway consumer-group
  methods; `EVENT_BUS_BACKEND` setting and factory (others recognised, raise).
- **StreamConsumer**: reusable runner (reclaim → read → handle → ack; dead-letter
  after max attempts; optional inbox dedupe) — the building block for Phase 7's
  per-domain workers.
- **RedisInbox** (`set_if_absent` SET NX EX): at-least-once → effectively-once.
- The worker relays the events stream through the publisher port
  (behaviour-identical serialization; engine command path unchanged).
- 17 new unit tests (bus mapping/DLQ, consumer retry/reclaim/dedupe); ruff +
  strict mypy clean; 233 backend unit/arch tests pass.

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
