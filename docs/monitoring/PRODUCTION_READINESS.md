# monitoring.v1 — production readiness

> **Superseded by [PRODUCTION_REVIEW.md](PRODUCTION_REVIEW.md).**
>
> This document concluded the controlled-staging phase and recommended that the
> work proceed to production *review*. That review has since been carried out
> and reached its own decision, on more evidence than was available here —
> including four production-deployment blockers found by reading the deployment
> manifests, which this document never examined.
>
> Kept because its matrix is the record of what staging actually proved. Where
> the two disagree, PRODUCTION_REVIEW.md is current.

## Decision (as at the end of controlled staging)

    READY FOR PRODUCTION REVIEW

Production **review** — not production deployment. Nothing in this phase touched
production DNS, firewalls, credentials, databases, brokers or trading, and the
decision to deploy is not being made here.

### Why "review" rather than "further controlled staging"

The previous phase ended at *further controlled staging* because PostgreSQL,
concurrency, restart, TLS and the critical failure modes were unknown. They are
not unknown now. Of the eleven blockers that phase listed, seven are closed with
evidence, three are owner decisions, and one is physically untestable on this
host.

More staging **on this machine cannot produce new information.** There is no
container runtime, no second host and no production-class hardware here, so the
three remaining technical gaps are not gaps that more of the same work would
close. The next step that produces information is a review in which the owner
settles three questions and decides whether to provision a container staging
environment.

## 1. Readiness matrix

`PASS` `PARTIAL` `FAIL` `NOT TESTED` `UNKNOWN` `OWNER DECISION`

| Gate | Status | Evidence |
|------|--------|----------|
| Canonical contract | PASS | Schema byte-identical to the producer's copy; vendored package untouched |
| Producer harness | PASS | **11/11 unmodified**, re-run after every change and under the least-privilege role |
| PostgreSQL | PASS | Migration, persistence, types, drift, downgrade/upgrade round-trip |
| Concurrency | PASS | 2/5/10/20 identical deliveries → exactly one acceptance; race found and fixed |
| Sequence correctness | PASS | 1,2,3 → 5 (409) → 4 → 5; refused sequence leaves no trace |
| Immutability | PASS | ORM, Core and raw SQL all refused; **and TRUNCATE, via role separation** |
| Quarantine | PASS | Separate, admin-only, bytes preserved, bounded |
| Projection | PASS | All knowledge states preserved; message types separated |
| Rebuild | PASS | Twice, identical, evidence unchanged hash-for-hash |
| Restart | PASS | Five scenarios; state reconstructed from PostgreSQL |
| DB outage | PASS | Bounded ~12 s 503, never a false ACK |
| DB recovery | PASS | Immediate, no duplicates |
| **Persistence interruption** | **PASS** | Transaction destroyed mid-flight; 9 checks |
| Storage failure | PARTIAL | Write-refusal covered two ways; **literal ENOSPC NOT TESTED** |
| TLS | PASS | Valid / expired / mismatch / untrusted each refused distinctly |
| Authentication | PASS | Publisher, admin, agent cross-use, foreign source |
| Security | PASS | Hostile-input battery; no leakage; bounded request bodies |
| Frontend composition | PASS | 12 assertions against real staging payloads |
| **Browser auth / tenancy** | **PASS** | Real JWT, session and membership; 8 checks |
| Multi-worker | PASS | 14 checks across two processes; safe, not enabled |
| Remote DB | **NOT TESTED** | Single host |
| Sustained load | PASS | 15 minutes; see `PERFORMANCE_BASELINE.md` |
| Performance | PASS | Matrix to concurrency 32, zero errors, ~327x headroom |
| Resource bounds | PARTIAL | Connections capped; **memory trend needs a longer run** |
| Retention | **OWNER DECISION** | Growth measured, options costed |
| Staging isolation | PASS | Separate databases, roles, credentials, port |
| LLS untouched | PASS | Zero files modified; schema byte-identical |
| Trading isolation | PASS | No control verb, no outbound client, no trading import |
| Container / orchestration | **NOT TESTED** | No container runtime on this host |
| Monitoring tenancy | **OWNER DECISION** | Not partitioned by organisation |

## 2. The three owner decisions

None of these is engineering work. All three are costed and evidenced.

### 2.1 Retention

`RETENTION_POLICY.md` costs three options against measured growth. At the
contract's maximum publication rate, evidence grows ~**17.6 GB/year** — which
makes "keep everything and bound only the rejected traffic" a genuinely viable
option rather than a deferral.

**Two questions:** how long must accepted evidence stay directly queryable, and
what window applies to quarantine and raw request bodies? The second can be
answered independently and closes the unbounded-growth concern on its own.

### 2.2 Monitoring tenancy

Monitoring data is scoped by deployment tier, never by organisation. Every
organisation with a `TRADING_VIEW` member sees the same data. Tenancy itself is
enforced correctly (403 for a foreign organisation), so this is a question of
intent, not a defect: is monitoring infrastructure telemetry for one operator, or
per-customer data?

### 2.3 Number of publishing LLS services

The per-service rate is a contract fact (0.1 msg/s maximum). How many services
will publish to one receiver in production is an owner input, and it multiplies
every capacity and storage figure.

## 3. Required before deployment (not before review)

1. **Deploy with a non-owning database role.** Demonstrated and verified in
   staging (`DEPLOYMENT_VALIDATION.md` §1). Without it, the append-only
   guarantee is one `TRUNCATE` from untrue.
2. **Keep the PostgreSQL logging invariant**: `log_parameter_max_length_on_error = 0`
   and `log_statement` at `none` or `ddl`, or full message bodies enter the
   database log.
3. **Keep `X-Forwarded-Proto` at the edge**, or a trailing-slash POST hands the
   producer a plaintext URL (`TLS_VALIDATION.md` §4.2).
4. **Provision a container staging environment** if orchestration behaviour needs
   validating before deployment — it could not be tested here.
5. **`REVOKE CONNECT ON DATABASE ... FROM PUBLIC`** so database separation is
   enforced rather than conventional.

## 4. What this phase changed in the product

| # | Defect | Severity | Status |
|---|---|---|---|
| 8 | Evidence table truncatable by the application's own credential | high | fixed — role separation, verified |
| 9 | Read-only database and revoked grant surfaced as 500, not the contract's 503 | medium | fixed — any write-preventing DB error maps to 503 |
| 10 | A fresh platform install was impossible (baseline migration) | high, pre-existing, platform | fixed — one line |
| 11 | Stop script killed the launcher, not the server (my tooling) | test integrity | fixed; affected measurements relabelled |

Phase one's seven defects are listed in `STAGING_VALIDATION.md` §5.

## 5. Known characteristics, explicitly accepted

* **Request serialisation.** The ingress is `async def` calling blocking database
  I/O, so requests do not overlap. Measured, understood, and **deliberately not
  changed**: the contract caps the producer at 0.1 msg/s single-flight against a
  receiver that sustains 32.7 msg/s on one worker. Changing it would spend
  correctness risk on ~327x surplus capacity. Revisit only if the producer's
  delivery model changes or many services publish to one receiver.
* **Monitoring shares a process and database role with the ops telemetry API.**
  A genuinely isolated receiver would be a separate deployment. Recorded, not
  attempted.
* **Immutability is PostgreSQL-only.** On SQLite the ORM guard is the whole
  guarantee. Fine for production; the asymmetry should be known.
* **`/health` is unauthenticated**, disclosing tier, schema versions, database
  reachability and a quarantine count.

## 6. Still not known

| Item | Why |
|---|---|
| Container and orchestration behaviour | No container runtime on this host |
| Remote database and cross-host latency | Single host |
| Production-class hardware | Developer machine |
| Multi-hour memory trend | 15-minute run — see §7 |
| Literal disk exhaustion | Unsafe to reproduce here |
| Production message-type mix | Fixture package is a correctness corpus, not a sample |

## 7. One measurement that needs a longer run

Under sustained load the receiver's resident memory rose steadily rather than
flattening — roughly 0.5 KB per accepted message across a 15-minute run. Whether
that is a genuine leak or Python allocator behaviour cannot be settled in
15 minutes, and it is **not** claimed either way.

At the contract's maximum rate this would be a few MB per day, which matters only
across months without a restart. It is listed as PARTIAL under resource bounds
rather than PASS, and a multi-hour run is the way to resolve it.

## 8. Decision

    READY FOR PRODUCTION REVIEW

Requested on the basis that every practical staging gate has been tested, the
remaining technical gaps need infrastructure this host does not have, and the
three open questions are decisions rather than work.

**Not** a claim of production readiness.
