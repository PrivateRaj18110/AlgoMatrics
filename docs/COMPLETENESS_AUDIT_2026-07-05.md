# Algo Matrics completeness audit

Audit date: 2026-07-05  
Scope: all 287 repository files across backend, frontend, SDKs, VPS agent,
database migration, tests, Docker, CI, documentation, and configuration.

## Executive result

The repository is a coherent, typed, modular **paper-trading SaaS prototype**.
It is not yet a production-grade live-trading platform and the prior
`PRODUCTION_READINESS.md` score of 88/100 is not supported by the implementation.

Current evidence-based assessment:

| Area | Status | Notes |
|---|---|---|
| Clean Architecture / DDD | Mostly complete | Domain separation is tested; several application contexts still import other contexts' infrastructure through explicit exceptions |
| Authentication / profile | Substantially complete | Refresh rotation, MFA, sessions, reset, API keys exist; concurrency, browser token exposure, and audit gaps remain |
| Organizations | Partial | CRUD/team/invitations exist; invitation link has no frontend route and multi-org creation has no UI |
| Billing | Partial | One-time checkout and period entitlements work; true recurring subscription renewal/provider state synchronization do not |
| Broker onboarding | Partial | Paper onboarding works; live symbol/token mapping, credential renewal, reconciliation, and safe MT5 agent discovery are missing |
| Dashboard / portfolio | Functional prototype | Backed by real queries, but error states, cache strategy, FX valuation, and analytics correctness need work |
| Strategy deployment | Partial | Built-ins and in-process uploads run; no lease/single-writer protection or secure isolation |
| Paper trading | Functional prototype | Domain and simulator are good; command transport can lose work during commits/restarts |
| Live trading | Unsafe / incomplete | Simulated market data can drive live orders; venue mappings and reconciliation are incomplete |
| Frontend | Broad but incomplete | Main pages use APIs; Logs, Portfolio, Watchlists, invitation acceptance, org creation, and several admin/API surfaces are absent |
| Tests | Insufficient | 32% backend line coverage; most API/routes/processes/adapters have zero direct coverage |
| Deployment | Local only | Compose works structurally; no production orchestration, TLS, secret manager, backup automation, observability stack, or deployment workflow |
| Security | Paper MVP only | Strong primitives exist, but uploaded strategy RCE, MT5 SSRF/agent auth, refresh races, and production configuration enforcement remain |

## Remediation progress

Validated after the initial audit:

- Refresh rotation now locks the token row; browser responses no longer expose
  refresh-token values.
- Invitation acceptance and organization creation are connected in the
  frontend.
- Uploaded Python strategies are disabled by default and remain unavailable in
  production until an isolated runner exists.
- Live trading now requires the organization setting, a verified connection,
  and a broker-specific venue instrument mapping. Live strategy runs fail
  closed while the only market-data source is simulated.
- MT5 agent URLs are parsed and restricted to an explicit host allowlist, with
  HTTPS required outside local/test environments. Agent authentication is
  fail-closed and also protects health data.
- `venue_instruments` and its administration APIs/UI were added in migration
  `0002`.
- Stripe/Razorpay recurring provider references, provider subscription state,
  replay-safe webhook receipts, renewal settlement, provider cancellation, and
  resumption were added in migration `0003`.
- Registration, reset, and invitation e-mails now use a transactional,
  retryable e-mail outbox added in migration `0004`.
- Engine commands are written to the database outbox in the same transaction
  as orders/runs. The relay publishes them after commit, and the engine uses a
  Redis consumer group with acknowledgement and stale-pending recovery.
- Frontend lint dependencies are pinned; Ruff, strict mypy, frontend lint,
  frontend production build, 97 Python tests, and 13 frontend tests pass.
- Watchlists, Portfolio (holdings/allocation), and Notifications history pages
  are implemented and wired to their existing live APIs, with routing,
  navigation, mutation hooks, and component tests. This closes the audit's
  watchlist, portfolio, and notifications-history frontend gaps. Frontend suite
  is now 17 tests.

The findings below preserve the original audit snapshot. Items explicitly
listed above are remediated; the remaining roadmap continues to be tracked
from this baseline.

## Inspection and verification evidence

- Repository inventory: 287 files.
- Backend route inventory: 112 FastAPI/OpenAPI routes including WebSocket.
- Persisted model inventory: 33 tables.
- Ruff: passed.
- Strict mypy: passed for 186 source files.
- Backend/SDK/agent tests: 85 passed, 6 infrastructure tests skipped because
  Docker is unavailable.
- Backend coverage: 32% (`10,066` statements, `6,852` missed).
- Frontend TypeScript production build: passed.
- Frontend Vitest: 11 passed.
- Frontend lint: **failed before linting** because
  `eslint-plugin-react-hooks` is imported but not declared/installed.
- Docker Compose and testcontainers could not be executed because Docker is
  unavailable in the audit environment.

## Critical and high-severity findings

### C1 — Uploaded strategy code executes in the trading-engine process

`validate_strategy_source` is only an AST screen. Uploaded source is passed to
`compile` and `exec` with normal Python builtins and process privileges.
Python sandboxing cannot be made safe with an AST denylist. A paper-only rule
does not protect the server, database credentials, broker KEK, network, or
other tenants.

Required:

- disable uploads in staging/production until an isolated runner exists;
- run untrusted code in a locked-down container/microVM with no host secrets,
  no ambient network, read-only filesystem, resource/time limits, and a narrow
  capability RPC;
- sign and scan strategy packages and record provenance.

### C2 — Live strategies can be driven by simulated market data

`MARKET_DATA_SOURCE` only supports `simulated`. The trading engine consumes the
same simulated `md:ticks` stream for paper and live strategy runs. There is no
venue-qualified live feed, freshness/sequence guard, or binding between an
account's venue instrument and the price used for risk/execution.

Required: prohibit live runs/orders until a verified venue data source and
freshness policy are attached to the account/instrument.

### C3 — Order and strategy commands are not transactionally durable

`OrderService` and strategy services write Redis `engine:commands` before the
request transaction commits. The engine can read before the row is visible,
Redis can succeed while PostgreSQL rolls back, or PostgreSQL can commit while
Redis fails. The transactional outbox is used for events but not engine
commands.

The engine starts `XREAD` at `$`, so commands already in the stream are ignored.
It uses no consumer group, acknowledgements, pending recovery, inbox table, or
command deduplication. Multiple engine replicas would process ticks/runs
unsafely and do not implement account/run leases.

Required: transactional command outbox, consumer groups, inbox/idempotency,
pending recovery, reconciliation, and distributed single-writer leases.

### C4 — Live instrument mapping is missing

The schema has only a global `instruments` table with `symbol` globally unique.
There is no `venue_instruments` table for broker/exchange symbol, token,
contract multiplier, expiry, tick/lot rules, or active mapping. Live routing
passes canonical symbols and an empty token to Indian adapters. Duplicate
symbols across venues cannot be represented safely.

### C5 — MT5 agent is not production safe

- Bearer auth silently disables when `AGENT_TOKEN` is unset.
- No mTLS, agent registration, certificate rotation, command journal, nonce,
  replay defense, signed upgrade, or lease.
- User-provided `agent_url` is fetched by API/engine, creating SSRF exposure.
- `/health` is unauthenticated and leaks account/currency state.
- MT5 stop/limit behavior is not implemented correctly: submission always uses
  `TRADE_ACTION_DEAL`; replace is a no-op; cancel does not validate retcodes.
- Simulator state is in-memory and appropriately test-only.

### H1 — Refresh-token rotation races

Concurrent refreshes can both observe an unused token and mint replacements
because the token row is not locked. The browser refresh response also returns
the raw refresh token in JSON even though it is placed in an HttpOnly cookie.

### H2 — E-mail is an unsafe in-transaction side effect

Registration and invitations send e-mail before the database transaction
commits. A later failure can deliver a dead link. SMTP latency also holds the
request transaction open. Delivery needs an outbox-backed asynchronous job.

### H3 — Live-trading organization setting is not enforced

`live_trading_enabled` can be changed in organization settings but is not
checked by order placement or run creation. Plan entitlement alone controls
live activity.

### H4 — Billing is not a recurring subscription system

Stripe uses `mode=payment`, Razorpay creates one-time orders, and no provider
subscription/customer/payment-method identifiers are modeled. At period end
the scheduler rolls paid users to a fallback plan instead of charging or
creating a renewal invoice. Provider cancellations, refunds, disputes,
chargebacks, taxes, dunning, and proration are not synchronized.

## Placeholder, stub, mock, and partial implementations

These are intentional protocols/defaults and are **not** unfinished:

- `...` in `Protocol` definitions;
- no-op optional Strategy SDK callbacks;
- `NotImplementedError` handling around Windows signal registration.

Actual partial implementations:

- MT5 `replace` is a no-op and non-market order semantics are incorrect.
- MT5/Indian/Delta adapters have no contract tests against recorded/sandbox
  responses and no durable broker reconciliation process.
- `market_data_source` supports simulated data only.
- strategy subscription methods only log that subscriptions were fixed at run
  creation.
- uploaded strategies run in-process; the documented container isolation is
  roadmap only.
- `events` Redis stream has no general consumer/inbox/DLQ/replay tooling.
- `OTEL_EXPORTER_OTLP_ENDPOINT` is present in `.env.example` but OpenTelemetry
  is not installed or configured.
- docs/blog on the landing page is explicitly a placeholder.
- Python SDK contains only package metadata; no generated REST/WebSocket client.

## Frontend completeness

### Pages connected to real APIs

Login, register, e-mail verification, forgot/reset password, dashboard,
strategies, strategy detail/runs/logs, brokers, orders, positions, trades,
analytics, risk, subscription, profile, organization settings, team, API keys,
notification settings, security, and the implemented admin sections call real
backend APIs.

### Missing or disconnected frontend workflows

- Invitation e-mails link to `/invitations/accept`, but the router/page does not
  exist. The link always reaches Not Found.
- Organization creation exists in the API but has no authenticated UI.
- Organization invitation acceptance exists in the API but has no UI.
- ~~Watchlist CRUD endpoints and hook exist but no page/component uses them.~~
  **Resolved:** `/app/watchlists` implements full CRUD with live quotes.
- Tenant audit endpoint and hook exist but no Logs/Audit page uses them.
  (Audit UI now exists at `/app/audit`.)
- Admin metrics and admin audit endpoints have no admin UI.
- Broker connection detail/update and account detail endpoints have no UI.
- Order detail/execution endpoint has no detail UI.
- Market candle endpoint has no chart/detail UI.
- ~~Analytics exposure endpoint has no UI.~~ **Resolved:** rendered on the
  Analytics page and the new Portfolio allocation view.
- Invoice detail endpoint has no detail/download UI.
- ~~No dedicated Portfolio page (only dashboard/analytics projections).~~
  **Resolved:** `/app/portfolio` holdings/allocation/accounts view.
- No general Logs page.
- ~~No Notifications page/history; only a bell popover.~~ **Resolved:**
  `/app/notifications` with All/Unread filtering and mark-as-read.
- No plan/provider availability UI; checkout can present unavailable paths.
- Most pages treat query errors as empty data rather than showing retry/error
  states.
- Only three frontend test files exist; responsive, accessibility, routing,
  settings, billing, trading, and admin workflows are untested.

## Backend endpoints without a frontend consumer

Operational/provider endpoints are intentionally headless (`health/*`,
payment webhooks). User-facing unconsumed endpoints:

- `POST /organizations`
- `POST /invitations/accept`
- `GET/PATCH /broker-connections/{id}`
- `GET /accounts/{id}`
- `GET /market-data/candles/{instrument_id}`
- `GET /orders/{order_id}`
- all watchlist mutations and watchlist display
- `GET /analytics/exposure`
- `GET /billing/providers`
- `GET /billing/invoices/{invoice_id}`
- tenant `GET /audit-events`
- admin `GET /metrics` and `GET /audit-events`

## Database and migration gaps

- Only one baseline migration exists and calls `Base.metadata.create_all`.
  It is not an explicit, reviewable production DDL history and migration tests
  also bypass Alembic by calling `create_all`.
- Missing `venue_instruments`/contract mappings.
- Missing `inbox_messages`, durable engine commands, consumer offsets, DLQ,
  agent identity/lease/heartbeat/journal, e-mail delivery outbox, webhook event
  receipts, provider customers/subscriptions, feature flags, and scoped
  settings tables.
- No PostgreSQL RLS policies despite architecture documentation.
- `risk_limits (organization_id, account_id)` permits duplicate organization
  defaults because PostgreSQL treats nullable unique values as distinct.
- Active kill switches have no partial unique constraint; concurrent duplicate
  switches are possible.
- `broker_order_id` is not uniquely constrained per account.
- `instruments.symbol` is globally unique and not venue-qualified.
- `invoices.provider_order_id` is neither provider-qualified nor unique.
- No partitioning or retention automation for audit/outbox/log/snapshot data.
- No FX rates or valuation currency tables; multi-currency portfolio totals add
  unlike currencies.
- No tax, refund, dispute, credit-note, payment-method, or recurring billing
  tables.
- No explicit optimistic-lock enforcement despite `version` columns.

## Missing tests

Measured non-infrastructure coverage is 32%. Direct coverage is zero for most
FastAPI routes, dependencies, middleware, WebSocket hub, user service,
portfolio service, strategy runtime/service, trading queries/watchlists,
live router, all live broker adapters, and all background processes.

Required additions:

- API contract tests for every route, permission, tenant isolation, validation,
  pagination, and RFC 9457 error;
- refresh concurrency/reuse and cookie tests;
- organization invitation and owner-transfer concurrency;
- recurring billing, duplicate webhooks, amount/currency mismatch, refunds and
  disputes;
- broker adapter conformance with recorded/sandbox fixtures;
- command outbox, consumer crash/retry, duplicate and pending recovery;
- strategy callback/order/position notifications and restart state;
- WebSocket ticket, authorization, subscription limits, reconnect and slow
  consumer;
- live-trading guardrails and stale-feed failures;
- migration upgrade from empty DB and schema/model drift check;
- frontend route/component/accessibility tests for every page;
- browser E2E for the complete signup → verify → subscribe → paper trade path;
- load/soak/chaos tests.

The existing integration/e2e tests use testcontainers but create schema from
ORM metadata rather than exercising Alembic. They were not runnable in this
environment because Docker is absent.

## Docker, deployment, and operations gaps

- No Kubernetes/ECS manifests, Terraform, production Compose override, or
  deployment workflow.
- No TLS termination/certificate automation; nginx listens on HTTP only.
- No cloud secret-manager integration or documented workload identity.
- `secrets-init` installs an unpinned package at container startup.
- Base images are mutable tags, not digest pinned.
- No SBOM, image signing, SAST, dependency, license, secret, or IaC scan in CI.
- No PostgreSQL backup/PITR automation or automated restore test.
- No Prometheus/Grafana/Loki/trace backend or alert rules.
- No resource requests/limits, autoscaling, disruption budgets, network
  policies, or egress restrictions.
- No zero-downtime expand/migrate/contract deployment enforcement.
- No VPS-agent packaging/service installer or secure update channel.
- Frontend ESLint dependencies are incomplete.

## Security gaps

- In-process untrusted strategy execution (critical).
- MT5 SSRF and bearer-token/optional-auth design (critical/high).
- No production startup validation for secure cookies, HTTPS app URL, console
  e-mail backend, CORS, secret source, simulated live feed, or upload isolation.
- Refresh rotation concurrency and raw refresh token response.
- No global authenticated API/user/tenant rate limits; most routes rely only on
  nginx per-IP limits.
- Account lockout can be abused for targeted denial of service and has no
  progressive challenge/notification.
- Uploaded avatar verifies MIME declaration, not image bytes, and uses
  synchronous filesystem I/O in an async handler.
- No CSP/HSTS header (HSTS requires HTTPS).
- No webhook event-ID receipt/replay store; payment idempotency is incomplete
  for ignored/failed duplicates.
- Payment settlement does not reject amount/currency mismatch against invoice.
- No security event alerts for suspicious refresh reuse, API-key use, role
  changes, or credential rotation.
- No RLS defense in depth.
- No dependency/container security gates.

## Performance and scalability gaps

- Market ticks use Redis Pub/Sub, so disconnects lose data and every engine
  instance receives all ticks.
- Strategy callbacks run sequentially in the tick loop; one callback can block
  all strategies for up to 10 seconds.
- Engine has no partition ownership/lease; horizontal scaling is unsafe.
- Outbox worker holds PostgreSQL row locks while making up to 400 Redis network
  calls per batch.
- Broker connection listing performs per-connection account queries (N+1).
- Portfolio analytics loads all executions and snapshots into Python memory;
  no pre-aggregated daily returns/performance projections.
- Snapshot writes grow every minute without retention/partitioning.
- API-key authentication writes `last_used_at` on every request.
- Rate limiting uses fixed windows and one Redis transaction per request.
- Request metrics are never recorded because middleware is registered without
  the `MetricsRecorder` created in lifespan.
- No cache headers/ETags for stable catalogs and no server-side query cache.
- No load budgets or measured capacity baseline.

## Incremental implementation order

### Phase 1 — SaaS control plane

1. Repair frontend lint/dependency gate.
2. Add invitation acceptance and multi-organization creation/switch UI.
3. Finish auth refresh concurrency/browser response hardening and audit.
4. Add production configuration validation and disable unsafe strategy uploads.
5. Complete recurring billing/provider synchronization and webhook validation.
6. Add venue instrument mappings and safe broker onboarding/reconciliation.
7. Add dashboard error handling and connect remaining Phase 1 endpoints.

### Phase 2 — trading product

1. Transactional command outbox, consumer groups, inbox, leases, recovery.
2. Harden paper lifecycle and strategy callback event delivery.
3. Add safe isolated strategy runner.
4. Add historical data/backtests.
5. Add portfolio/FX, Sharpe/Sortino, exposure UI, Logs/Audit UI, Watchlists.
6. Complete risk monitoring, notifications history/preferences, and admin.
7. Add real venue-qualified market data before enabling live mode.

### Phase 3 — production hardening

RLS, caching/read projections, partitioning/retention, OpenTelemetry,
Prometheus/Grafana/Loki, alerting/runbooks, backup/restore automation,
production IaC/orchestration, agent mTLS and signed updates, security CI,
integration/browser E2E, load/soak/chaos tests, and controlled live canaries.
