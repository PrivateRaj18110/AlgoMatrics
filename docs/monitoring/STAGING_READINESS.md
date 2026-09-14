# monitoring.v1 receiver — staging readiness

**Nothing was deployed.** No DNS, firewall, production secret, production credential or production database was touched. LLS was not modified.

---

## 1. Acceptance gates

| Gate | Status |
|---|---|
| Canonical schema unchanged | **PASS** — byte-identical to the producer's package, hash-guarded by two tests |
| 19/19 LLS fixtures accepted | **PASS** |
| Negative fixtures correctly handled | **PASS** — all six, each with the contract's expected status |
| Canonical JSON | **PASS** — `canonical_json(parse(raw)) == raw` for all 19 |
| Whole-request hash | **PASS** — matches the producer manifest for all 19 |
| Authentication | **PASS** |
| Identity | **PASS** — content address recomputed, forgery refused |
| Duplicate | **PASS** — including ACK-loss and after-later-sequence |
| Sequence semantics | **PASS** — 409 on gap and unknown-older, last accepted state retained |
| Freshness semantics | **PASS** — asserted state read, no horizon, no timer |
| Environment semantics | **PASS** — two axes, never derived from one another |
| Runtime semantics | **PASS** — array preserved |
| Evidence immutability | **PASS** — ORM-enforced, update and delete both refused |
| Quarantine | **PASS** — separate from dead-letter, admin-only, original bytes kept |
| Projection rebuild | **PASS** — identical and idempotent, evidence untouched |
| API | **PASS** — every producer object passes through verbatim |
| UI | **PASS** for components and client logic; **NOT TESTED** for page composition |
| Security | **PARTIAL** — hostile input exercised; TLS not tested |
| 61 skipped capabilities migrated | **PASS** — 75 executing, all passing |
| No invented values | **PASS** |
| No `stale_after` in monitoring.v1 | **PASS** — removed from columns, service, API, frontend and tests |
| **PostgreSQL migration** | **NOT RUN** |
| **PostgreSQL E2E** | **NOT RUN** |
| **Restart** | **NOT TESTED** |
| **Failure / recovery** | **NOT TESTED** |
| **Concurrent delivery** | **NOT TESTED** |
| **Performance** | **UNKNOWN — NOT MEASURED** (every metric) |
| Staging isolation | **PARTIAL** — enforced in the query and tested on SQLite; not verified on PostgreSQL |
| Production credentials absent | **PASS** — none configured, none used |
| LLS untouched | **PASS** |

## 2. Performance

**No measurement was carried out.** Every metric below is `UNKNOWN — NOT MEASURED`:

messages/sec · request latency · DB latency · projection latency · CPU · memory · storage growth · concurrent publishers · concurrent dashboard viewers · large valid messages · burst traffic · slow clients

No deterministic synthetic generator was built. The producer's 22-message package is a correctness fixture, not a load profile — the largest message is 98 KB and the set exercises no sustained rate.

The only timings observed are test-suite wall clock, which is not performance data: the ops suite is 15m03s, dominated by pre-existing phase-3 simulation tests; the monitoring receiver file is 75 tests in ~38s, dominated by per-test app construction and SQLite setup.

**No capacity claim should be made about this receiver.**

## 3. Failure isolation

Structurally, LLS cannot be affected by this receiver:

- no callback, no reverse connection, no shared database, filesystem or process
- a receiver failure returns 503, and the producer's durable queue absorbs it — the contract's own retry table says `5xx` means retry with backoff and `Never backpressure Core`
- `test_receiver_refuses_rather_than_accepting_into_nothing` asserts the receiver returns 503 rather than acknowledging data it cannot store

**This is a design property, verified by structure and by one test — not by taking a component down under load.**

## 4. Open items before production review

1. **PostgreSQL.** Everything has run on SQLite. The migration is additive DDL plus drops of never-deployed tables; it needs a real run and a timing.
2. **Concurrency.** The duplicate path has an `IntegrityError` branch that returns `duplicate` rather than failing, but no test races two deliveries of the same content address. On PostgreSQL the unique constraint is the real guarantee; that needs exercising.
3. **Quarantine retention is unbounded.** `monitoring_quarantine` and `monitoring_raw_requests` grow without limit. A publisher stuck on an unsupported version sending 1 MiB messages grows raw storage by one body per request. **This must be decided before production review** — either a bounded retention policy, or an explicit documented decision that it remains staging-only.
4. **Gzip decompression has no byte ceiling** in the shared middleware. The effective 1 MiB limit is still enforced for monitoring.v1 (a decompressed body over the limit is refused 413); the exposure is memory during decompression. Fix and rationale in `RECEIVER_SECURITY.md` §10.
5. **TLS untested.** Certificate validation, hostname validation, expired-certificate rejection and redirect downgrade have not been exercised. Staging ran over plain HTTP on loopback.
6. **Set `MONITORING_DEPLOYMENT_ENVIRONMENT` explicitly** on every deployment. Unset means `UNKNOWN`, which is safe but means projections land in an `UNKNOWN` tier and production queries will not see them.

## 5. Configuration required

```
MONITORING_SOURCE_TOKENS="lls-monitoring-staging:<token>"
MONITORING_ADMIN_TOKEN=<token>
MONITORING_DEPLOYMENT_ENVIRONMENT=staging
OPS_DATABASE_URL=<staging postgres>
MONITORING_SCHEMA_DIR=<path to schemas/monitoring-v1 in the image>
```

Generate credentials with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

No nginx change is required — `/ops/api/` already proxies to ops-api, so the ingress is reachable at `https://<host>/ops/api/monitoring/v1/messages`.

`MONITORING_SCHEMA_DIR` matters if `ops/backend` is containerised without the repository root: the receiver reads the canonical schema from disk and returns 503 if it cannot find it. Verify in the built image, not only in the repo.

## 6. Decision

Correctness against the canonical contract is demonstrated by the producer's own harness. What has never been exercised is the database the receiver will actually run on, its behaviour under concurrency and restart, and its cost under any load at all.

That is precisely the gap a controlled staging integration closes, and it is not a gap more local testing can close.

**READY FOR CONTROLLED STAGING**
