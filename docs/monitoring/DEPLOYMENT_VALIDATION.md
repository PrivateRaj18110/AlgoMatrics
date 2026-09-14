# monitoring.v1 — deployment validation

Companion to `STAGING_VALIDATION.md`. Covers the database privilege model, the
process model, logging exposure, and what remains untested about deployment.

## 1. The evidence table could be destroyed by the application's own credential

### The finding

The append-only guarantee added in the previous phase is enforced by a row-level
trigger that refuses UPDATE and DELETE. Measured at the start of this phase:

| | |
|---|---|
| Table owner | `algomatric_staging` — **the application's own role** |
| `has_table_privilege(..., 'TRUNCATE')` | **true** |
| Row triggers fire on TRUNCATE | **no** |

So a single `TRUNCATE monitoring_evidence` from the credential the receiver uses
every day would empty the forensic record, and the trigger would not fire. The
privilege cannot be revoked either: `REVOKE TRUNCATE` does not apply to a table's
owner.

This is not a defect in the trigger. It is a gap in the **deployment model**: the
application was running as the owner of the tables it is supposed to be unable to
rewrite.

### The model, demonstrated

Two roles, which is the smallest arrangement that closes it:

| Role | Purpose | Rights on `monitoring_evidence` |
|---|---|---|
| **owner** (`algomatric_staging`) | owns the tables, runs migrations, used by operators and by the test suite | full, including TRUNCATE |
| **receiver** (`algomatric_receiver`) | the running application | **SELECT, INSERT only** |

The receiver role holds full DML on every other table — see §2 for why — and is
explicitly stripped back on evidence after the blanket grant.

### Verified

Measured against the real database with the receiver's own credential:

| Attempt | Result |
|---|---|
| `TRUNCATE monitoring_evidence` | REFUSED — permission denied |
| `DELETE FROM monitoring_evidence` | REFUSED — permission denied |
| `UPDATE monitoring_evidence` | REFUSED — permission denied |
| `DROP TABLE monitoring_evidence` | REFUSED |
| `ALTER TABLE ... DISABLE TRIGGER` | REFUSED |
| `INSERT` new evidence | **allowed** |
| `DELETE FROM monitoring_projections` (rebuild) | **allowed** |
| `UPDATE monitoring_sequence_state` | **allowed** |

And the receiver still works. Running the staging deployment under this role, the
producer's unmodified acceptance harness passes **11/11** — so the restriction
costs nothing the contract needs.

**This is now the staging configuration, not a proposal**: the staging receiver
runs as `algomatric_receiver`. The test suite continues to use the owner role,
because its teardown legitimately truncates.

### Required for production

Deploy the application with a role that does **not** own the monitoring tables.
Migrations run as the owner; the application does not. Without that separation,
the append-only guarantee is one statement away from being untrue.

## 2. The receiver is not a separate process

Discovered while applying the model above: starting the ops backend under a
monitoring-only grant failed at startup with `permission denied for table
machines`.

The same process serves **both** the monitoring.v1 receiver and the
agent-telemetry API, against one database with one credential. So:

* "Least privilege for the receiver" necessarily means least privilege for the
  whole ops backend. The grant has to cover everything that process touches.
* The evidence restriction still achieves its purpose — the credential cannot
  destroy evidence — which is the property that matters.
* A genuinely isolated monitoring receiver would be a separate deployment. That
  is a larger change than this phase should make, and it is recorded rather than
  attempted.

## 3. Logging exposure

Reviewed against §30.

| Check | Result |
|---|---|
| Application logs in the monitoring path | **none** — the receiver emits no logs of its own; only uvicorn access lines |
| Credentials in receiver logs | **none found** (publisher, admin, agent tokens all searched) |
| Credentials in the PostgreSQL log | **none found** |
| Message bodies in the PostgreSQL log | **none** — `log_parameter_max_length_on_error = 0` by default, so bound parameters are not logged |
| Message identities in the PostgreSQL log | present, in constraint-violation details (`Key (message_id)=(mon1/…)`) |

Message identities appearing in a database log is appropriate: a content address
is an identity, not payload, and it is what makes a duplicate-race investigable.

### Deployment invariant

**`log_parameter_max_length_on_error` must stay `0`, and `log_statement` must
stay `none` or `ddl`.** Raising either writes full monitoring message bodies into
the PostgreSQL log, which has different retention and access control from the
evidence table. The defaults are correct; the risk is a well-meaning change.

Related: PostgreSQL grants `CONNECT` on a database to `PUBLIC` by default. A
production deployment should `REVOKE CONNECT ON DATABASE ... FROM PUBLIC` so
that database separation is enforced rather than conventional.

## 4. A fresh platform install was impossible

Found while standing up the platform for the authentication test, and outside
the monitoring subsystem.

`backend/migrations/versions/0001_baseline.py` builds the baseline with
`Base.metadata.create_all()` over **live ORM models**, and keeps a hand-maintained
list of tables belonging to later revisions so they are excluded. Its own comment
states the hazard:

> failing to pin this list would make a fresh install create future tables
> before their explicit Alembic migrations run

Migration `0015` added `workspace_tasks` without adding it to that list, so on a
fresh database the baseline created the table and `0015` then failed with
`DuplicateTableError`. **No fresh platform database could be created.**

Existing deployments are unaffected — they migrated before `0015` existed — which
is why it went unnoticed.

Fixed by adding the missing entry, which is the mechanism the file already
documents. Verified: a fresh database now migrates to head `0015` with 52 tables.

Classification: **PRE-EXISTING, platform, found incidentally.** Recorded here
because a monitoring phase found it and because it blocks any new environment.

## 5. Observability of the receiver itself

What the deployment exposes about its own health, against the list §29 asks for:

| Signal | Exposed | Where |
|---|---|---|
| Receiver status | yes | `GET /health` |
| Contract/schema availability | yes | `GET /health` — `contractAvailable`, `supportedSchemaVersion` |
| Database configured | yes | `GET /health` — `storageConfigured` |
| **Database reachable** | yes | `GET /health` — `databaseReachable`, reported separately |
| Quarantine count | yes | `GET /health` — `UNKNOWN` when it cannot be read |
| Accepted count | yes, per publisher instance | `GET /sources` — `acceptedCount` |
| Duplicate count | yes, per instance | `GET /sources` — `duplicateCount` |
| Sequence refusal count | yes, per instance | `GET /sources` — `refusedGapCount`, `refusedOldCount` |
| Last accepted message / source / instance / sequence | yes | `GET /sources` |
| **Aggregate error count** | **not exposed** | — |
| **Storage growth** | **not exposed** | — |

Nothing fabricates a value. When the quarantine count cannot be read the
endpoint returns the string `UNKNOWN` and HTTP 503, rather than a zero — the
distinction §29 insists on, and one the previous behaviour (a bare 500) did not
make either way.

### The two gaps, and why they were not simply added to `/health`

`/health` is the **only unauthenticated endpoint** in the monitoring surface:

| Endpoint | Credential |
|---|---|
| `POST /messages` | publisher token |
| `GET /state`, `/evidence/{id}`, `/history`, `/sources` | dashboard viewer |
| `GET /quarantine` | administrator token |
| `GET /health` | **none** |

Adding aggregate error counts and storage growth there would widen what an
unauthenticated caller learns about the deployment. The per-instance counters
that carry most of that information already sit behind a credential on
`/sources`, which is the right side of the line. If the aggregates are wanted,
they belong behind the administrator token — recommended, not built, because
§51's "smallest safe implementation" applies and nothing currently needs them.

That `/health` is unauthenticated at all is itself a deliberate-choice item: it
discloses the deployment tier, schema versions, database reachability and a
quarantine count. Low sensitivity, and convenient for an orchestrator probe, but
it should be a decision rather than an accident.

## 6. A note on rotating the receiver credential

Recorded because it cost time during this phase and will cost an operator more.

The staging receiver runs as `algomatric_receiver`. Rotating that role's password
without restarting the receiver leaves the process holding a credential the
server no longer accepts, and **every request then fails with 503** — which
looks exactly like a database outage and is not one. The receiver's own health
endpoint reports `databaseReachable: false`, correctly, which is the signal that
distinguishes the two.

Any credential rotation must update the deployment's configuration and restart
the receiver in the same operation.

## 7. The deployment manifests, read for the first time

Everything above validates the receiver *running*. The production review then
read `deploy/docker/ops-api.Dockerfile` and `deploy/k8s/*` — which no earlier
phase had examined — and found four defects that staging could not have caught,
because staging never used those files.

This is worth recording as a methodology finding, not just a list: **a component
can be thoroughly validated and still be undeployable**, and the artefacts that
decide that are not exercised by any amount of testing the component itself.

| # | Defect | Consequence if deployed as it stood | Fixed in |
|---|---|---|---|
| 1 | The canonical schema was not copied into the image | The receiver would refuse **every** message, while `/api/health` — used by both probes — kept reporting the pod healthy. `schema_dir()` also indexed `parents[4]`, which does not exist in the image layout, so the failure surfaced as an unhandled `IndexError`/500 rather than the 503 callers handle. | `ops-api.Dockerfile`, `app/monitoring/contract.py` |
| 2 | No guard against a half-configured receiver | Publisher credentials present but no deployment tier meant evidence would be written under the tier `UNKNOWN` — and evidence is append-only, so it could never be corrected. | `app/core/config.py` |
| 3 | The application and migrations shared one `DATABASE_URL` | The application would have run as the table owner, which is exactly the condition §1 shows makes the append-only guarantee one `TRUNCATE` away from untrue. | `deploy/k8s/45-ops.yaml` (new `ops-migration-secrets`) |
| 4 | Volume and memory limits contradicted the measurements | The 256Mi limit sat **inside** the measured 220-233 MiB working range, so the pod would have been OOMKilled under load; the 10Gi volume was under one year at the contract maximum for a single publisher. | `deploy/k8s/45-ops.yaml`, `46-ops-db.yaml` |

Defect 2 is the one worth dwelling on. An *unconfigured* receiver is a coherent
safe state: no credentials means every upload is refused 401, which is obvious
and harmless. A *half*-configured receiver is the dangerous shape, because it
accepts connections, reports healthy, and writes unfixable data. The guard
therefore refuses to boot only when credentials are present and the rest is not
— it never blocks the safe state.

Verified by test (`tests/test_production_safety.py`): unconfigured boots, fully
configured boots, credentials without a tier refuses, credentials without a
loadable schema refuses, and the refusal message contains no credential
material.

## 8. Not tested

| Item | Status | Why |
|---|---|---|
| Docker / Kubernetes deployment artefact | **NOT TESTED** | No container runtime on this host |
| Linux production runtime | **NOT TESTED** | Staging ran on Windows |
| Multi-host networking | **NOT TESTED** | Single host |
| Secret injection from a real secret manager | **NOT TESTED** | Staging used environment files in a scratchpad |
| Health-check and restart policy under an orchestrator | **NOT TESTED** | No orchestrator |
| Production-class hardware | **NOT TESTED** | Developer machine |

None of these is claimed. The PostgreSQL semantics, privilege model, TLS
behaviour and failure handling validated here are independent of the container
runtime; the orchestration behaviour is not, and remains open.
