# monitoring.v1 — receiver documentation

Reports from the implementation of the LLS Monitoring Export receiver on algomatric.in.

**Start here:** [PRODUCTION_REVIEW.md](PRODUCTION_REVIEW.md) — the production review and
deployment gate: every category classified, what is proven and what is not, and why the gate
is closed.

**If you are the owner:** [OWNER_DECISIONS.md](OWNER_DECISIONS.md) — the three questions
only you can answer, with the measured consequence of each option.

The canonical wire contract is [`schemas/monitoring-v1/`](../../schemas/monitoring-v1), owned by the LLS producer.

### Production review (current)

| Document | Covers |
|---|---|
| [PRODUCTION_REVIEW.md](PRODUCTION_REVIEW.md) | **current status** — the full classification matrix and the gate decision |
| [OWNER_DECISIONS.md](OWNER_DECISIONS.md) | the four decisions, **all recorded 2026-09-13** — indefinite evidence, 30-day rejected traffic, organisation-partitioned, 1 publisher |
| [TENANCY_IMPACT_ASSESSMENT.md](TENANCY_IMPACT_ASSESSMENT.md) | what organisation partitioning requires — **the one blocker that needs building, not validating** |
| [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) | the ordered procedure for when the gate opens; **nothing in it has been run** |

### Controlled staging validation

| Document | Covers |
|---|---|
| [STAGING_VALIDATION.md](STAGING_VALIDATION.md) | every staging gate, the eleven defects found, and the decision that led to review |
| [POSTGRESQL_VALIDATION.md](POSTGRESQL_VALIDATION.md) | compatibility audit, migration, persistence, concurrency, rebuild |
| [FAILURE_RECOVERY.md](FAILURE_RECOVERY.md) | database outage, recovery, restart, persistence interruption, storage refusal |
| [TLS_VALIDATION.md](TLS_VALIDATION.md) | certificate matrix, the producer harness over HTTPS, transport semantics |
| [PERFORMANCE_BASELINE.md](PERFORMANCE_BASELINE.md) | measurements and their limits, including the 4.17 h / 746,400-message memory characterisation |
| [RETENTION_POLICY.md](RETENTION_POLICY.md) | **DECIDED 2026-09-13**: evidence indefinite, rejected traffic 30 days — with the measured growth behind it |
| [PRODUCTION_CAPACITY_MODEL.md](PRODUCTION_CAPACITY_MODEL.md) | contract publication rate, measured storage, and the two projection scenarios — **storage binds before throughput** |
| [DEPLOYMENT_VALIDATION.md](DEPLOYMENT_VALIDATION.md) | database privilege model, process model, logging exposure |
| [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) | the readiness assessment that concluded staging; superseded by PRODUCTION_REVIEW.md |

### Implementation reports

| Document | Covers |
|---|---|
| [STAGING_READINESS.md](STAGING_READINESS.md) | the previous phase's gates, superseded by STAGING_VALIDATION.md |
| [RECEIVER_IMPLEMENTATION.md](RECEIVER_IMPLEMENTATION.md) | architecture, pipeline, sequence, freshness, environments, storage |
| [RECEIVER_SECURITY.md](RECEIVER_SECURITY.md) | credentials, spoofing, hostile input, audit, known exposure |
| [RECEIVER_TEST_REPORT.md](RECEIVER_TEST_REPORT.md) | results, matrix coverage, every failure classified |
| [LLS_CONTRACT_RECONCILIATION.md](LLS_CONTRACT_RECONCILIATION.md) | how the canonical contract was adopted |
| [LLS_STAGING_E2E_VALIDATION.md](LLS_STAGING_E2E_VALIDATION.md) | the validation run that found the mismatch |
| [LLS_CONTRACT_COMPATIBILITY_REPORT.md](LLS_CONTRACT_COMPATIBILITY_REPORT.md) | exact field-by-field comparison of the two contracts, with proposed owner per difference |
| [FINAL_REPORT.md](FINAL_REPORT.md) | what was implemented, tested, verified, and what is unknown or blocked |
| [CONTRACT_IMPLEMENTATION_REPORT.md](CONTRACT_IMPLEMENTATION_REPORT.md) | how each contract clause was implemented; the one clarification the contract needed |
| [MONITORING_V1_RECEIVER_REPORT.md](MONITORING_V1_RECEIVER_REPORT.md) | validation order, acknowledgement semantics, idempotency, sequence, conflict, versioning |
| [UNKNOWN_STALE_IMPLEMENTATION_REPORT.md](UNKNOWN_STALE_IMPLEMENTATION_REPORT.md) | UNKNOWN end to end, STALE from publisher horizons, the dead-feed and recovery cases |
| [QUARANTINE_REPORT.md](QUARANTINE_REPORT.md) | quarantine vs dead-letter, what is preserved, why it is administrator-only |
| [PROJECTION_MODEL.md](PROJECTION_MODEL.md) | evidence/projection separation, keying, ordering, rebuild |
| [API_MONITORING_REPORT.md](API_MONITORING_REPORT.md) | both API surfaces and the provenance every response carries |
| [FRONTEND_MONITORING_REPORT.md](FRONTEND_MONITORING_REPORT.md) | which UI is authoritative (a correction), and how the nine states render |
| [SECURITY_REPORT.md](SECURITY_REPORT.md) | credential model, scope enforcement, audit, and one unfixed exposure |
| [PERFORMANCE_REPORT.md](PERFORMANCE_REPORT.md) | what was **not** measured, and what is therefore unknown |
| [TEST_REPORT.md](TEST_REPORT.md) | results, the required matrix, and every failure classified |
| [BACKUP_RESTORE.md](BACKUP_RESTORE.md) | what is irreplaceable and what is rebuildable |

Reports below [FINAL_REPORT.md](FINAL_REPORT.md) describe the receiver as built against the
**superseded** `monitoring-export/v1` proposal. They remain accurate about the receiver's
architecture — evidence immutability, quarantine, projections, environment isolation — and
inaccurate about the wire format. Read them with
[LLS_CONTRACT_RECONCILIATION.md](LLS_CONTRACT_RECONCILIATION.md) alongside.
