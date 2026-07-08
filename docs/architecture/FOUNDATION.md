# Algo Matrics Foundation Architecture

Status: accepted foundation  
Horizon: 5–10 years  
Style: Clean Architecture, DDD, event-driven, multi-tenant by construction

## 1. Executive design

Start as a **modular monolith plus specialized runtimes**, not as dozens of microservices.
The API/control plane owns ordinary transactional workflows. Trading engine, market-data
ingestion, scheduler, asynchronous workers, and edge agents are separate processes from
day one because they have different latency, availability, and scaling profiles.

PostgreSQL is authoritative. Redis is used for cache, short-lived locks, rate limits,
presence, and stream fan-out; no irreplaceable state lives only in Redis. Durable events
are inserted into a PostgreSQL outbox in the same transaction as aggregate changes.
A relay publishes them to Redis Streams initially. Kafka/Redpanda can replace the relay
transport when sustained volume, retention, or independent consumer count warrants it.

Trading uses a broker-neutral canonical model. Strategies submit intents through a
capability-limited context; risk policy approves or rejects them; an execution service
routes approved orders through a broker port. Venue adapters translate capabilities,
symbols, quantities, order types, statuses, and errors. Strategy code never imports a
broker SDK.

### Quality attributes

| Attribute | Foundation decision |
|---|---|
| Safety | Fail closed for live orders; kill switches at platform, tenant, account, strategy, and instrument scopes |
| Consistency | Strong consistency inside an aggregate; eventual consistency across contexts |
| Availability | Control-plane degradation must not terminate healthy running strategies; agents use leases and bounded offline behavior |
| Scalability | Stateless APIs; partitioned workers by account/run/instrument; hot market data separated from OLTP |
| Auditability | Immutable audit/event records, correlation IDs, actor identity, policy decision evidence |
| Extensibility | Ports/adapters, versioned events and SDK, broker capability discovery |
| Tenancy | `organization_id` on every tenant-owned row and event, enforced in repository filters and PostgreSQL RLS |

## 2. Repository structure

The tree lists required destinations even where only a representative foundation file is
currently scaffolded.

```text
algo-matrics/
├── backend/
│   ├── src/algo_platform/
│   │   ├── api/
│   │   │   ├── dependencies/          # auth, tenant, UoW, pagination
│   │   │   ├── middleware/            # request ID, logging, rate limit, errors
│   │   │   ├── routes/                # /api/v1 REST composition
│   │   │   ├── websocket/             # authenticated channels and backpressure
│   │   │   └── app.py
│   │   ├── modules/
│   │   │   ├── identity/              # authentication, users, tokens, RBAC
│   │   │   ├── organizations/         # tenants, memberships, entitlements
│   │   │   ├── brokerage/             # broker catalog, credentials, accounts
│   │   │   ├── instruments/           # canonical instruments and venue mappings
│   │   │   ├── strategies/            # definitions, versions, deployments, runs
│   │   │   ├── trading/               # orders, executions, trades, positions
│   │   │   ├── risk/                  # limits, policy evaluation, kill switches
│   │   │   ├── portfolio/             # balances, valuations, PnL, exposure
│   │   │   ├── market_data/           # subscriptions, ticks, order books, candles
│   │   │   ├── historical_data/       # backfill, datasets, quality, retention
│   │   │   ├── notifications/         # templates, preferences, delivery
│   │   │   ├── audit/                 # actor/action evidence
│   │   │   ├── scheduling/            # calendars and durable jobs
│   │   │   ├── feature_flags/         # staged activation and entitlements
│   │   │   └── settings/              # scoped, versioned runtime configuration
│   │   ├── shared/
│   │   │   ├── domain/                # IDs, money, events, errors
│   │   │   ├── application/           # UoW, clock, publisher ports
│   │   │   └── infrastructure/        # DB, Redis, telemetry, encryption
│   │   ├── processes/
│   │   │   ├── api.py                 # FastAPI control plane
│   │   │   ├── trading_engine.py      # strategy/execution orchestration
│   │   │   ├── market_data.py         # live feed ingest/normalization
│   │   │   ├── worker.py              # outbox and async consumers
│   │   │   └── scheduler.py
│   │   └── config.py
│   ├── migrations/                    # Alembic revisions; forward-only in prod
│   └── alembic.ini
├── frontend/
│   ├── src/
│   │   ├── app/                       # providers, router, error boundary
│   │   ├── api/                       # generated client and query keys
│   │   ├── auth/
│   │   ├── components/{ui,charts,trading}/
│   │   ├── features/{dashboard,strategies,brokers,orders,positions,trades}/
│   │   ├── features/{portfolio,analytics,logs,risk,settings,admin}/
│   │   ├── hooks/                     # WebSocket and shared hooks
│   │   ├── pages/
│   │   ├── stores/                    # local UI state only
│   │   └── types/                     # generated schemas preferred
│   ├── e2e/
│   ├── package.json
│   └── vite.config.ts
├── packages/
│   ├── python-sdk/                    # public REST/WebSocket client
│   ├── strategy-sdk/                  # stable strategy author contract
│   ├── event-schemas/                 # JSON Schema/AsyncAPI, compatibility tests
│   └── typescript-sdk/                # generated browser/client types
├── agents/vps-agent/
│   ├── src/algo_agent/
│   │   ├── broker_plugins/            # MT5/local venue bridges
│   │   ├── control/                   # registration, leases, commands
│   │   ├── execution/                 # local command executor/idempotency
│   │   ├── telemetry/                 # heartbeats, logs, metrics
│   │   ├── security/                  # mTLS identity and secret access
│   │   └── main.py
│   ├── packaging/                     # systemd/Windows service
│   └── tests/
├── deploy/
│   ├── compose/                       # local and single-VPS topology
│   ├── docker/                        # non-root multi-stage images
│   ├── nginx/                         # TLS, proxy, WebSocket, security headers
│   ├── kubernetes/{base,overlays}/    # future multi-node deployment
│   ├── terraform/{modules,environments}/
│   └── observability/{grafana,prometheus,loki,otel}/
├── config/{local,test,staging,production}/
├── docs/
│   ├── architecture/{adr,diagrams}/
│   ├── api/                           # OpenAPI and AsyncAPI
│   ├── operations/                    # runbooks, SLOs, DR
│   ├── security/                      # threat model and key rotation
│   └── development/
├── tests/
│   ├── unit/                          # domain/application, no infrastructure
│   ├── integration/                   # Postgres/Redis/adapters
│   ├── contract/                      # broker/event/API contracts
│   ├── architecture/                  # forbidden-import rules
│   ├── performance/                   # event and order-path budgets
│   └── e2e/
├── scripts/                           # repeatable operator/developer commands
├── .github/workflows/
├── pyproject.toml
├── .env.example
└── README.md
```

Within every bounded context, use:

```text
module/
├── domain/          # entities, value objects, domain services/events, repository protocols
├── application/     # commands, queries, handlers, DTOs, ports, policies
├── infrastructure/  # SQLAlchemy, broker/vendor clients, Redis, repositories
└── presentation/    # routers, consumers, serializers; no business rules
```

## 3. Dependency flow

```text
                 API / WS / event consumers
                            │
                            ▼
                    Application use cases
                    │                 ▲
                    ▼                 │ ports
                 Domain               │
                    ▲                 │
                    └──── Infrastructure adapters
                         PostgreSQL / Redis / brokers
```

Allowed dependencies point inward: presentation → application → domain. Infrastructure
implements application/domain ports and is wired only in composition roots. Contexts do
not import another context's infrastructure or ORM models. Cross-context interaction is
through public application facades for synchronous checks, or versioned integration
events for asynchronous propagation.

`shared` contains only stable technical/domain primitives. It must not become a dumping
ground for business logic. No cyclic context dependencies are permitted.

## 4. Bounded contexts and responsibilities

| Module | Responsibility and reason |
|---|---|
| Authentication | Password/OIDC login, MFA extension point, access and rotated refresh tokens, sessions; isolates security-critical lifecycle |
| Users | Profile, status, preferences; identity is distinct from tenant membership |
| Organizations | Tenant, membership, role assignment, plan and entitlement boundaries |
| Brokers | Venue catalog, capabilities, encrypted credentials, symbol mappings, connectivity |
| Accounts | Broker accounts/subaccounts, mode, base currency, reconciliation state |
| Strategies | Metadata, immutable versions, artifacts, approvals, deployments and runs |
| Strategy Engine | Sandboxed lifecycle, subscriptions, callbacks, state checkpoints and supervision |
| Orders | Intent and order state machine, idempotency, broker linkage, cancel/replace |
| Trades/Executions | Immutable fills and execution quality; one order may have many fills |
| Positions | Quantity, cost basis, realized/unrealized state, hedging versus netting rules |
| Portfolio | Cross-account valuation, cash, exposure, PnL snapshots and performance |
| Risk Engine | Pre-trade limits, continuous risk, kill switches and decision evidence |
| Market Data | Feed subscriptions, normalization, deduplication, fan-out and freshness |
| Historical Data | Backfills, candles, datasets, quality metadata and retention policies |
| Live Data | A deployment/runtime concern within Market Data, isolated from historical queries |
| Event Bus | Outbox relay, schemas, retries, inbox dedupe and dead-letter handling |
| Notifications | User preferences and email/SMS/webhook/in-app delivery |
| Logging | Structured operational telemetry with redaction; not a business datastore |
| Audit | Immutable security/business actions with actor and before/after metadata |
| Metrics | Technical and business counters/histograms without high-cardinality IDs |
| Health Monitoring | Liveness, dependency readiness, broker/agent heartbeat and stale-feed detection |
| Scheduler | Exchange calendars, market jobs, retries; emits commands instead of executing domain logic |
| Feature Flags | Safe rollout, tenant entitlement and emergency disable; not authorization |
| Settings | Versioned global/organization/account/strategy settings with precedence and validation |

Authentication and Users may initially share the Identity context. Orders, Trades, and
Positions may initially share Trading. The table boundaries remain explicit so they can
be extracted without changing domain contracts.

## 5. Trading and strategy engine

### Lifecycle

```text
Draft → Validated → Approved → Deployed → Starting → Running
                                      ↘ Failed
Running → Pausing → Paused → Starting
Running/Paused → Stopping → Stopped
Running → Degraded → Stopping/Running
```

1. Validate package manifest, SDK/API version, parameters, resource budget, and signature.
2. Resolve deployment policy, broker account, data subscriptions, and risk profile.
3. Acquire a lease keyed by strategy run; only its holder may process callbacks.
4. Restore versioned strategy state and reconcile orders/positions before becoming live.
5. Deliver ordered events per strategy run through a bounded mailbox.
6. Checkpoint state and event cursor. On shutdown, stop intake, drain within a deadline,
   persist, release subscriptions, then release the lease.

Untrusted marketplace strategies run in isolated containers/microVMs with CPU, memory,
network, filesystem, and time limits. In-process plugins are permitted only for trusted,
reviewed first-party code.

### Order path

```text
Market event → strategy callback → SignalGenerated → OrderIntent
 → entitlement/session checks → pre-trade risk decision
 → durable Order(PENDING/APPROVED) + outbox in one DB transaction
 → execution router → account-partitioned command queue
 → broker adapter/edge agent → venue acknowledgement/fill
 → inbox dedupe → order state machine → fills → position projection
 → portfolio/risk projections → WebSocket and notifications
```

Every command carries `command_id`, `correlation_id`, `causation_id`, tenant, account,
strategy run, deadline, and idempotency key. Ordering is guaranteed only inside a key
(account/order/run), never globally. Broker timeouts are **unknown outcomes**, not
failures: reconcile by client ID before retrying. At-least-once delivery plus inbox
deduplication is preferred over claiming impossible end-to-end exactly-once semantics.

### Broker abstraction

`BrokerExecutionPort` covers connect/health, submit/cancel/replace, and order updates.
`BrokerAccountPort` covers balances, orders, and positions. Separate market-data and
historical-data ports avoid forcing all venues into one oversized interface.

Adapters:

- MT5: normally executed by the Windows/VPS agent; normalize lots, retcodes, terminal
  connectivity, hedging/netting, and symbol suffixes.
- NSE brokers: one adapter per broker behind a shared Indian-market utility layer;
  normalize exchange/product/variety, freeze quantities, tick size, and trading sessions.
- Crypto/Delta: normalize perpetual/future instruments, contract multipliers, funding,
  reduce-only, leverage, liquidation, and 24×7 sessions.
- Paper: deterministic fill model with venue calendars, bid/ask, latency, partial fills,
  fees, slippage, rejects, and reproducible seeds.

Each adapter exposes a capability descriptor. Unsupported order types fail during
validation, before routing. A conformance suite runs identical submit/cancel/fill and
reconciliation scenarios against every adapter.

## 6. Strategy SDK

Developers subclass `Strategy` and optionally implement `initialize`, `on_tick`,
`on_candle`, `on_signal`, `on_order_update`, `on_position_update`, and `shutdown`.
The runtime supplies `StrategyContext`, the only route to subscriptions, state, signals,
and order requests.

SDK guarantees:

- immutable, timezone-aware event DTOs using `Decimal` for price/quantity;
- semantic versioning and declared compatibility range;
- deterministic clock/randomness in backtests;
- bounded callback deadlines and mailbox backpressure;
- namespaced, versioned state with migration hooks;
- no credential access and no direct broker/network access by default;
- identical lifecycle contract for backtest, paper, and live modes;
- package manifest: ID, version, entry point, parameters schema, required data,
  permissions, resource limits, SDK range, checksum/signature.

`on_signal` enables composition, but signals are facts/events—not an instruction to
bypass risk. Slow strategies receive coalesced ticks or are paused according to policy;
the execution path is never allowed unbounded queues.

## 7. Data model

All mutable tables include `id UUID`, `organization_id UUID`, `created_at timestamptz`,
`updated_at timestamptz`, and `version bigint` for optimistic concurrency unless noted.
Money, price, and quantity use explicit `numeric(p,s)` chosen per instrument class, never
floating point. All timestamps are UTC; exchange timezone is metadata.

### Core schema and relationships

```text
organizations 1─* memberships *─1 users
organizations 1─* broker_connections 1─* trading_accounts
brokers 1─* broker_connections
instruments 1─* venue_instruments *─1 brokers

strategies 1─* strategy_versions 1─* strategy_deployments
strategy_deployments 1─* strategy_runs
strategy_runs *─1 trading_accounts

trading_accounts 1─* orders 1─* executions
strategy_runs 1─* orders
instruments 1─* orders/executions/positions
trading_accounts 1─* positions
positions 1─* position_lots        (when lot accounting is required)

risk_profiles 1─* risk_limits
risk_assignments → organization/account/strategy
risk_decisions *─1 orders

portfolio_snapshots 1─* portfolio_snapshot_items
audit_log, outbox_events, inbox_messages, event_store (append-only)
agents 1─* agent_leases / agent_heartbeats
```

Important columns:

- `users(email_ci unique, password_hash, status, mfa_state)`
- `refresh_tokens(user_id, session_id, token_hash, family_id, expires_at, revoked_at)`
- `broker_connections(broker_id, credential_ciphertext, key_version, status)`
- `trading_accounts(connection_id, external_account_id, mode, base_currency)`
- `strategy_versions(strategy_id, semver, artifact_uri, checksum, manifest_json, status)`
- `strategy_runs(deployment_id, account_id, mode, state, lease_owner, last_event_cursor)`
- `orders(account_id, run_id, instrument_id, client_order_id, broker_order_id, side,
  type, tif, quantity, prices, status, filled_quantity, average_price, raw_ref)`
- `executions(order_id, broker_execution_id, quantity, price, fee, fee_currency,
  liquidity, executed_at)`
- `positions(account_id, instrument_id, side_or_net, quantity, average_price,
  realized_pnl, last_mark, as_of)`
- `risk_decisions(order_id, policy_version, result, reason_codes, inputs_json)`
- `audit_log(actor_type/id, action, resource_type/id, request_id, ip_hash,
  before_json, after_json, occurred_at)`
- `outbox_events(event_id, aggregate_type/id/version, event_type, schema_version,
  payload, headers, occurred_at, published_at, attempts)`
- `inbox_messages(consumer, event_id, received_at, processed_at, result)`

### Constraints and indexes

- Unique `(organization_id, lower(email))` where tenant-local email is intended;
  global unique lower(email) for the chosen identity model.
- Unique `(account_id, client_order_id)` and `(account_id, broker_order_id)` when known.
- Unique `(broker_id, broker_execution_id)` prevents duplicate fills.
- Unique `(consumer, event_id)` implements inbox idempotency.
- Unique `(aggregate_type, aggregate_id, aggregate_version)` preserves event order.
- Partial indexes on open orders and active runs:
  `orders(account_id, created_at) WHERE status IN (...)`.
- Query indexes begin with `organization_id`, then common filters/time:
  `(organization_id, account_id, executed_at DESC)`.
- BRIN on large append-only timestamp tables; B-tree for point/range operational access.
- GIN only for proven JSONB predicates. Important business fields remain typed columns.
- Check constraints for positive quantity, status-dependent prices, and fill bounds.
- Foreign keys are retained inside a database boundary; use soft delete only when legally
  or operationally necessary.

### Partitioning and storage tiers

Do not partition small tables prematurely. Partition `ticks`, `order_book_updates`,
`audit_log`, `outbox_events`, and potentially `executions` by monthly/daily time ranges
after measured thresholds. Use subpartitioning/hash by instrument only for genuine hot
spots. Automate partition creation and retention.

PostgreSQL/TimescaleDB can serve an initial tick workload, but raw high-volume ticks and
books should move to object storage as compressed Parquet, cataloged by
venue/instrument/date, with ClickHouse/another analytical store added when query volume
justifies it. OLTP stores canonical orders/fills and recent aggregates, not indefinite
raw feeds.

RLS uses a transaction-local organization setting and policies on tenant tables. Admin
and worker roles are separate. Application repository filters remain defense in depth.

## 8. Event system

Canonical envelope:

```json
{
  "event_id": "uuid",
  "event_type": "trading.order_filled.v1",
  "schema_version": 1,
  "occurred_at": "2026-07-03T10:00:00Z",
  "organization_id": "uuid",
  "aggregate": {"type": "order", "id": "uuid", "version": 4},
  "correlation_id": "uuid",
  "causation_id": "uuid",
  "producer": "execution-service",
  "payload": {}
}
```

Required domain/integration events:

| Event | Producer | Primary consumers |
|---|---|---|
| `MarketDataReceived` | feed adapter | candle builder, strategy engine, recorder |
| `SignalGenerated` | strategy engine | audit, UI, optional signal composition |
| `OrderSubmitted` | trading | execution router, audit, UI |
| `OrderFilled` | execution/trading | positions, portfolio, risk, notifications |
| `PositionOpened` | positions | portfolio, risk, UI |
| `PositionClosed` | positions | portfolio, analytics, notifications |
| `RiskViolation` | risk | kill-switch workflow, alerting, audit |
| `StrategyStarted` | strategy engine | UI, monitoring, audit |
| `StrategyStopped` | strategy engine | UI, monitoring, cleanup |

Events are past tense and immutable. Commands are imperative and may be rejected.
Schemas live in `packages/event-schemas`, are backward compatible, and are checked in CI.
Consumers retry with exponential backoff and jitter, classify permanent errors, then
dead-letter with replay tooling. Payloads contain no secrets or unnecessary PII.

Market ticks are a high-volume stream, not business outbox events. They use a specialized
data plane with sequence/freshness checks; only derived business facts enter the durable
business bus.

## 9. REST and WebSocket API

Base: `/api/v1`; OpenAPI is the source for generated SDKs. Use cursor pagination for
time-ordered resources. Mutations accept `Idempotency-Key`; optimistic updates use ETag
or expected version. Errors use RFC 9457 Problem Details with stable machine codes.

```text
POST   /auth/login                     POST /auth/refresh
POST   /auth/logout                    GET  /me
GET    /organizations                  POST /organizations
GET    /members                        POST /members/invitations

GET    /brokers                        POST /broker-connections
POST   /broker-connections/{id}/verify
GET    /accounts                       POST /accounts/{id}/reconcile

GET    /strategies                     POST /strategies
POST   /strategies/{id}/versions       POST /strategy-runs
POST   /strategy-runs/{id}:start       POST /strategy-runs/{id}:pause
POST   /strategy-runs/{id}:stop        GET  /strategy-runs/{id}

GET    /orders                         POST /orders
POST   /orders/{id}:cancel             POST /orders/{id}:replace
GET    /trades                         GET  /positions
GET    /portfolios/{id}/summary        GET  /portfolios/{id}/performance

GET    /risk/profiles                  PUT  /risk/profiles/{id}
POST   /risk/kill-switches              DELETE /risk/kill-switches/{id}
GET    /risk/violations

GET    /market-data/instruments        GET /historical/candles
GET    /dashboard/summary              GET /analytics/*
GET    /audit-events                   GET /logs/search
GET    /metrics/business               GET /health/dependencies
GET    /agents                         GET /agents/{id}/health
GET    /settings                       PUT /settings/{scope}/{key}
GET    /feature-flags                  PUT /feature-flags/{key}
```

WebSocket `/api/v1/ws` authenticates during upgrade using a short-lived socket ticket,
then uses subscribe/unsubscribe messages for `orders`, `positions`, `portfolio`,
`strategy-runs`, `risk`, `notifications`, and authorized market-data channels. Each
message has type, schema version, sequence, timestamp, and payload. Enforce per-connection
subscription limits, bounded send queues, heartbeat, resume cursor, and slow-consumer
disconnect. Never put long-lived access tokens in URL query logs.

## 10. Frontend

React Router supplies route-level splitting; TanStack Query owns server state and cache;
a small local store owns ephemeral UI state. Forms use generated Pydantic/OpenAPI schemas
or compatible TypeScript validators. Tailwind and accessible headless primitives form a
shared design system.

Pages: Login/MFA, Dashboard, Strategy Management/version/deployment/run detail, Broker
Accounts/connectivity, Orders, Positions, Trades, Portfolio, Analytics, Logs, Risk limits
and violations, Settings, and tenant/platform Admin. Every dangerous action shows scope,
mode (paper/live), account, consequence, and confirmation. Live mode is visually
unambiguous. Stale data and disconnected feeds are first-class states, never silently
displayed as current.

The browser consumes projections, not raw domain tables. Authorization is enforced by
the API; hidden buttons are only UX.

## 11. Security

- Short-lived asymmetric JWT access tokens (`iss`, `aud`, `sub`, `sid`, `jti`, tenant,
  permissions); keys rotate by `kid`. Refresh tokens are opaque, random, hashed at rest,
  rotated on every use, and reuse revokes the family.
- Prefer secure HttpOnly SameSite cookies for browser refresh tokens; protect cookie
  mutations against CSRF. Store access tokens in memory, not local storage.
- RBAC roles map to granular permissions; resource ownership, live-trading approval, and
  risk limits add ABAC checks. Default deny. Support MFA and step-up authentication for
  credentials, live enablement, withdrawals (if ever supported), and kill-switch release.
- Broker secrets use envelope encryption with a cloud KMS/Vault KEK and per-record DEKs.
  Agents receive scoped, short-lived credentials where vendor support allows. Secrets
  never enter images, Git, metrics, events, traces, or normal logs.
- TLS everywhere; mTLS for agents/service identity. Encrypt disks, databases, backups,
  and object storage. Pin agent identity and rotate certificates.
- Rate-limit by IP, user, organization, route, and order/account budget. WAF limits are
  supplemental; the risk engine remains authoritative.
- Pydantic validates shape; domain objects validate invariants; adapters treat broker
  responses as untrusted. Parameterize SQL, constrain uploads, scan strategy artifacts,
  and prohibit unsafe deserialization.
- Structured redaction allowlist, tamper-evident/append-only audit export, synchronized
  clocks, least-privilege DB roles, dependency/SAST/container/IaC/secret scanning.
- Threat model explicitly covers account takeover, strategy supply chain, replay,
  duplicate orders, stale prices, compromised agent, confused deputy, tenant leakage,
  log injection, SSRF, and denial of wallet/order capacity.

## 12. Deployment and operations

```text
                         Internet
                            │
                     CDN/WAF/LB/Nginx
                       ┌────┴────┐
                    React      FastAPI pods
                                  │
               ┌──────────────────┼───────────────────┐
          PostgreSQL HA       Redis HA          Object storage
               │                  │
        outbox workers       streams/cache
               │                  │
       Trading engine workers ────┤── Market-data workers
               │
       mTLS command/event gateway
         ┌─────┴─────────┐
     VPS Agent A     VPS Agent N
     MT5/broker      MT5/broker

All components → OpenTelemetry Collector → Prometheus/Grafana + Loki + trace backend
```

Docker images are multi-stage, pinned by digest, non-root, read-only where possible, with
separate API/worker/engine commands from one backend image. Compose supports local and a
single VPS. Production uses managed PostgreSQL/Redis/object storage and Kubernetes/ECS
only when operational capacity supports it. Never place MT5 terminal assumptions inside
cloud API containers; the edge agent owns them.

CI pipeline:

1. Ruff format/lint, mypy, frontend lint/typecheck.
2. Unit and architecture tests.
3. PostgreSQL/Redis integration and Alembic upgrade tests.
4. Broker, event-schema, OpenAPI compatibility contracts.
5. Build SBOM; secret, dependency, SAST, image and IaC scans.
6. Build/sign immutable images and artifacts.
7. Deploy ephemeral/staging, run smoke/E2E and paper canary.
8. Manual protected approval for production/live-sensitive changes.
9. Progressive rollout; automatic rollback on technical SLOs, but database migrations
   use expand/migrate/contract and are backward compatible.

Environment configuration is validated at startup and injected externally. No staging or
production secrets in `.env` files. Feature flags separate deployment from release.

Backups: PostgreSQL PITR with encrypted continuous WAL and daily snapshots; object-store
versioning/replication; configuration and audit export. Define target RPO/RTO per tier
(recommended starting point: ≤5 minutes/≤60 minutes for trading records). Quarterly
restore drills prove recovery. Broker reconciliation rebuilds external truth after
recovery; Redis reconstruction is expected.

Observe order-decision latency, venue acknowledgement latency, rejects, unknown outcomes,
reconciliation drift, stale feed age, event lag/DLQ, strategy callback time, lease churn,
risk violations, DB/Redis saturation, agent heartbeats, and WebSocket drops. Alerts link
to runbooks and avoid tenant/account labels in globally scraped metrics.

Scaling:

1. Scale stateless API and read replicas.
2. Partition engine consumers by `account_id` or `strategy_run_id`; preserve single
   writer for an order/account state machine.
3. Partition market data by venue/instrument and share upstream subscriptions.
4. Separate read models/analytics from OLTP.
5. Adopt Kafka/Redpanda and ClickHouse only after measured Redis/Postgres limits.
6. Regionalize market-data and execution near venues; keep tenant home region and
   explicit cross-region failover to prevent split-brain order submission.

## 13. Coding and testing standards

- Python modules/functions `snake_case`, classes `PascalCase`, constants `UPPER_CASE`;
  events past tense, commands imperative, IDs explicit (`account_id`, never generic `id`
  at boundaries).
- Full type hints; `Decimal` for financial values; aware UTC datetime; frozen value
  objects; no primitive strings for critical enums/IDs inside domain code.
- Constructor injection and small ports; no service locator or global clients. Keep
  domain pure and application handlers orchestration-focused.
- SOLID and DRY apply to stable concepts, not speculative generic frameworks. Prefer
  readable explicit mappings at broker boundaries.
- Logs are structured with timestamp, severity, service, environment, request/correlation
  IDs, event type, and safe tenant reference. Never log tokens, credentials, full broker
  payloads, or personal data.
- Unit tests cover aggregates, risk policy, position arithmetic, state machines, calendar
  boundaries, and failure paths. Property tests target fill/position invariants.
- Integration tests use real PostgreSQL/Redis containers. Broker sandboxes and recorded
  fixtures support adapter tests; paper engine has deterministic golden scenarios.
- Contract tests enforce every broker adapter and event evolution. E2E tests cover
  login → connect paper account → deploy strategy → fill → position → stop.
- Performance tests establish budgets for tick fan-out and order path. Chaos tests cover
  duplicate/lost/delayed events, agent disconnect, broker timeout, stale feed, DB
  failover, and process restart.
- Coverage is a signal, not the target; 100% is required for critical risk/order state
  transitions and lower thresholds may apply to glue code.

## 14. Key trade-offs

| Decision | Benefit | Cost / mitigation |
|---|---|---|
| Modular monolith control plane | Transactions and refactoring stay simple | Enforce context boundaries with import tests; extract by pressure |
| PostgreSQL outbox + Redis Streams first | Low operational burden, durable publication | Redis is not long-retention bus; maintain transport port and migration criteria |
| At-least-once processing | Realistic across broker/network boundaries | Mandatory idempotency, inbox, reconciliation |
| Agent for VPS/broker terminals | Handles MT5 and network locality cleanly | More trust surface; mTLS, signed upgrades, least privilege, leases |
| Shared canonical instrument/order model | Strategies remain portable | Venue features can be lost; expose capabilities and extension metadata |
| Containers for untrusted strategies | Marketplace isolation | Startup/compute overhead; trusted first-party fast path is separately governed |
| CQRS projections without full event sourcing | Fast reads and good auditability | Projections are eventually consistent; authoritative aggregates stay in OLTP |

## 15. Development roadmap

### Phase 0 — engineering baseline (weeks 1–3)

Monorepo tooling, ADRs, CI security gates, local Compose, settings, structured logging,
OpenTelemetry, health checks, PostgreSQL/Redis, Alembic, test factories, architecture
tests, secret/key development workflow.

### Phase 1 — secure multi-tenant control plane (weeks 4–8)

Identity, refresh rotation, organizations/RBAC/RLS, broker catalog/connections, encrypted
credentials, account verification, audit log, admin shell, agent registration/mTLS.

### Phase 2 — paper vertical slice (weeks 9–14)

Instrument master, live/historical data ports, deterministic paper broker, strategy SDK
and lifecycle, order/risk/fill/position path, outbox/inbox, WebSocket projections, basic
dashboard. Prove restart/replay and reconciliation before live connectivity.

### Phase 3 — first live venue (weeks 15–20)

MT5 agent adapter or one selected Indian broker, capability/conformance suite, account
reconciliation, stale-price guard, hierarchical kill switches, live approvals, canary
limits, operational runbooks and restore drill.

### Phase 4 — portfolio and operations (weeks 21–28)

Multi-account portfolio/PnL, fees and FX, risk dashboards, notification policies,
scheduler/exchange calendars, SLO alerts, HA deployment and performance/chaos tests.

### Phase 5 — multi-venue scale (months 8–12)

Additional NSE and Delta adapters, shared feed subscriptions, partitioning, analytical
store/object lake, account/run sharding, regional edge routing, billing/entitlements.

### Phase 6 — marketplace and AI (year 2+)

Signed strategy packages, review pipeline, sandbox isolation, licensing/revenue share,
version pinning and rollback. AI modules are advisory by default with provenance,
evaluation, drift controls, explicit permissions, and the same risk/order gates as every
other strategy—never a privileged path to brokers.

### Exit criteria for live trading

No phase enters live mode until duplicate submission, timeout reconciliation, partial
fills, restart recovery, stale data, kill switches, credential rotation, backup restore,
tenant isolation, and broker conformance have automated evidence and an owned runbook.

