# monitoring.v1 — receiver documentation

Reports from the implementation of the LLS Monitoring Export receiver on algomatric.in.

**Start here:** [STAGING_READINESS.md](STAGING_READINESS.md) — current status and acceptance gates.

The canonical wire contract is [`schemas/monitoring-v1/`](../../schemas/monitoring-v1), owned by the LLS producer.

| Document | Covers |
|---|---|
| [STAGING_READINESS.md](STAGING_READINESS.md) | **current status** — acceptance gates, open items, decision |
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
| [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) | verified vs unverified, and the prerequisites for deployment |

Reports below [FINAL_REPORT.md](FINAL_REPORT.md) describe the receiver as built against the
**superseded** `monitoring-export/v1` proposal. They remain accurate about the receiver's
architecture — evidence immutability, quarantine, projections, environment isolation — and
inaccurate about the wire format. Read them with
[LLS_CONTRACT_RECONCILIATION.md](LLS_CONTRACT_RECONCILIATION.md) alongside.
