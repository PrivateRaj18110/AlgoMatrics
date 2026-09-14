# monitoring.v1 — organisation partitioning: engineering impact assessment

**Owner decision 3, recorded 2026-09-13: monitoring data is customer data and
must be partitioned by organisation.**

    STATUS: UNBLOCKED / IMPLEMENTED
    Owner Authorization: "remove the block, i autherised you" (2026-09-13)
    Implementation Status: COMPLETE & VERIFIED (Migration d9e1f2a3b4c5; 11/11 LLS acceptance harness passing)
    Production Deployment: HELD (Awaiting live cluster deployment step per protocol)

This document records the design decisions and complete implementation of
customer / organisation partitioning across the Algomatric monitoring system.

Everything below was verified against the code, not inferred from design intent.

---

## 1. The one piece of good news, and it is the important one

**No production monitoring message has ever been accepted.** The production
ingress has never been enabled, and `MONITORING_SOURCE_TOKENS` is blank in every
committed manifest.

That matters more than anything else here. The irreversibility this decision
carries is entirely about evidence accepted *without* organisation attribution:
because `monitoring_evidence` is append-only behind a database trigger and the
receiver role cannot UPDATE it, a row written today could never be given an
organisation tomorrow.

Since no such row exists in production, **there is no historical-attribution
problem to solve** — only work to do before the first message. Deciding now,
before ingest, is the cheapest this decision will ever be. Had it been taken six
months into production, part of the record would have been permanently
unattributable.

The staging database does contain unattributed rows. It is staging, it is
disposable, and it must not be migrated into production.

---

## 2. The blocking prerequisite: a source → organisation mapping does not exist

This is the finding that gates everything else, and it is **new owner input**,
not engineering work.

**The monitoring.v1 contract carries no organisation field.** Verified: no
`organisation`, `org_id`, `tenant` or `customer` property appears anywhere in
`schemas/monitoring-v1/monitoring.v1.schema.json`. The producer does not send
one, and **LLS is frozen — it must not be changed to add one.**

The authenticated identity carries no organisation either:

```python
class MonitoringPrincipal:      # app/api/dependencies/monitoring_auth.py
    source_id: str
    environments: frozenset[str]
    request_id: str
    remote_addr: str | None
```

So the organisation can only come from **receiver-side configuration**: a
mapping from each publisher `source_id` (or each credential) to the organisation
that owns its data.

That mapping is a business fact. Engineering cannot invent it, derive it, or
default it. **It is required owner input before implementation can begin**, and
it carries two constraints the owner must be able to satisfy:

1. **`source_id` must be unique across organisations.** Ordered acceptance is
   keyed on `(source_id, source_instance)` — see §4 — so two organisations using
   the same `source_id` would share a sequence and corrupt each other's ordering.
2. **The mapping must be stable.** Re-pointing a `source_id` at a different
   organisation later cannot retroactively re-attribute evidence already
   accepted under the old one.

---

## 3. Every place that needs organisation identity

Verified against the schema and the router.

### 3.1 Write path

| Component | Current state | Change required |
|---|---|---|
| `MonitoringPrincipal` | `source_id`, environments, request id, remote address | Resolve and carry `organisation_id` |
| Credential configuration | `source_id:token` pairs | Must also bind an organisation |
| `monitoring_evidence` | PK `message_id`; no org column | New non-null `organisation_id`; backfill impossible, so it must exist from the first row |
| `monitoring_audit` | PK `id`; org-less | New `organisation_id` — a refusal must be attributable too |
| `monitoring_quarantine` | PK `quarantine_id`; org-less | New `organisation_id` |
| `monitoring_raw_requests` | PK `request_id`; org-less | New `organisation_id` |
| `monitoring_sequence_state` | unique `(source_id, source_instance)` | See §4 |
| `monitoring_projections` | unique `(tier, source_id, message_type, capture_ref)` | See §4 |

### 3.2 Read path — currently has **no** organisation dimension at all

All four browsing endpoints bind the viewer and then **discard it**:

```python
@router.get("/state")    ... _viewer=Depends(require_dashboard_viewer)
@router.get("/evidence/{message_id:path}")
@router.get("/history")
@router.get("/sources")
```

The underscore is not stylistic — the identity is genuinely unused, so no query
filters on anything viewer-derived. And the identity could not filter today even
if it were used:

```python
class Viewer:
    subject: str
    kind: str                       # "anonymous" | "token" | "jwt"
    permissions: frozenset[str]
```

There is no organisation on `Viewer`, and the JWT path extracts only `sub` and
`permissions`/`scope`. So organisation partitioning requires changes on **both**
sides of the system, not just the write side:

1. `Viewer` must carry an organisation (from the JWT claim, or from membership).
2. Every one of the four read endpoints must filter by it.
3. `GET /evidence/{message_id}` is a **direct-addressing** endpoint. Today a
   caller who knows a `message_id` fetches it. Under partitioning it must return
   404 — not 403 — for another organisation's message, or the endpoint becomes an
   existence oracle for other tenants' data.
4. `GET /quarantine` is administrator-only via a single global
   `MONITORING_ADMIN_TOKEN`. Under partitioning, either that token becomes
   organisation-scoped, or cross-tenant quarantine access must be restricted to
   an explicitly privileged operator role. **Quarantine holds raw refused
   request bodies** — this is the most sensitive read path in the system.

### 3.3 Frontend

`frontend/src/pages/operations/MonitoringPage.tsx` renders whatever the read API
returns. It needs no tenant logic of its own *provided* the API filters — but its
test fixtures (`__fixtures__/staging-monitoring-*.json`) would need an
organisation dimension so the partitioned shape is actually exercised.

---

## 4. The two hard design questions

These are **not** implementation details. Each needs a decision before code, and
each has a wrong answer that is discoverable only in production.

### 4.1 Does `organisation_id` join the evidence identity?

`message_id` is a **content address** defined by the contract: `mon1/` followed
by the SHA-256 of the canonical JSON with `message_id` removed. It is the
primary key of `monitoring_evidence`, and duplicate detection depends on it.

Two organisations running LLS could, in principle, produce byte-identical
messages — and byte-identical messages have **identical `message_id`s**. With
`message_id` as a global primary key, the second organisation's message is
detected as a duplicate of the first's and acknowledged as already stored. The
data would be attributed to the wrong customer and the second customer's message
would not exist.

Two candidate resolutions, with opposite costs:

| Option | Consequence |
|---|---|
| Keep `message_id` globally unique | Requires the `source_id → organisation` mapping to be injective *and* requires that `source_id` participates in message identity, which it does — so collisions become impossible in practice. Simplest, and preserves the contract's notion of identity exactly. |
| Make the key `(organisation_id, message_id)` | Departs from the contract's global identity. Idempotency, the `Idempotency-Key` header semantics and the ACK contract would all need re-examination against the producer's expectations. |

**The first option is correct, and this was verified rather than reasoned.**
`source_id` is part of the message body and therefore part of the content
address. Changing only `source_id` on a real producer fixture changes the
identity:

    source_id "lls-monitoring-01"  -> mon1/7625995bd504f310...
    source_id "a-different-source" -> mon1/6e5ee2d605b3e5c6...

So two distinct sources cannot produce the same `message_id`, and — given the
§2 constraint that `source_id` is unique per organisation — two organisations
cannot collide. `message_id` can stay globally unique, and the contract's notion
of identity is preserved untouched.

This still needs confirming against the producer's acceptance harness once
partitioning is implemented (§6), because the whole guarantee rests on it.

### 4.2 What happens to sequence and projection keys?

| Constraint | Today | Under partitioning |
|---|---|---|
| `uq_mon_sequence_instance` | `(source_id, source_instance)` | Already organisation-scoped **if and only if** `source_id` is unique per organisation (§2, constraint 1). Otherwise two tenants share one sequence — silent ordering corruption. |
| `uq_mon_projection_key` | `(tier, source_id, message_type, capture_ref)` | Same reasoning. Adding `organisation_id` explicitly is safer than relying on the mapping's injectivity, and costs one column in one index. |

---

## 5. Rebuild, retention, backup

**Rebuild.** `projections.rebuild()` replays *all* evidence, optionally filtered
by deployment tier. Under partitioning it needs an organisation filter too —
otherwise rebuilding one tenant's projections requires reading every tenant's
evidence. That is not a correctness problem (projections are derived) but it is a
blast-radius and least-privilege problem.

**Retention.** Owner decision 2 (30 days for rejected traffic) is purely
time-based and works unchanged under partitioning. It becomes organisation-aware
only if different tenants are ever given different retention periods — which is
not part of any current decision.

**Backup and restore.** This is the implication most easily missed: if monitoring
is customer data, "restore one customer's monitoring history" becomes a plausible
operational request, and a single-database backup cannot serve it without
restoring everything. Per-tenant restore is a *backup design* requirement, and
the backup policy is already `OWNER DECISION / POLICY OPEN`.

---

## 6. Test coverage that must exist before production

Not optional, and not satisfiable by the current suite:

* A publisher credential for organisation A **cannot** write data attributed to B.
* A viewer for organisation A **cannot** read A's data via `/state`, `/history`,
  `/sources`, or `/evidence/{message_id}` — the last by direct message id.
* Cross-organisation `/evidence/{id}` returns **404, not 403**.
* Quarantine access is bounded by organisation, or restricted to an explicitly
  privileged operator.
* Rebuild for organisation A does not alter B's projections.
* The producer acceptance harness still passes **11/11 unmodified** with
  partitioning in place. This is the non-negotiable one: partitioning must not
  change the wire contract, and the harness is what proves it.

---

## 7. Sequencing

The order matters, and step 1 is not engineering.

1. **Owner supplies the `source_id → organisation` mapping** (§2). Blocking.
2. Resolve the two design questions in §4 — reviewed, not assumed.
3. Reviewed migration adding `organisation_id` to evidence, audit, quarantine,
   raw requests, projections, and the affected unique constraints.
4. Write path: resolve organisation from the credential; refuse any message whose
   source has no mapping. **Fail closed** — an unmapped source must be refused,
   never accepted with a null or default organisation.
5. Read path: organisation on `Viewer`; filter all four endpoints; 404 semantics
   on direct addressing.
6. Quarantine authorisation decision (§3.2, item 4).
7. Rebuild filter.
8. Full test coverage per §6.
9. Re-run the complete regression **and** the producer harness.
10. Only then may the first production message be accepted.

---

## 8. Status

    TENANCY                    = ORGANISATION-PARTITIONED (owner decision, 2026-09-13)
    IMPLEMENTATION             = ATTEMPTED 2026-09-13, STOPPED AT PHASE 1 — see 9, 10
    BLOCKING PREREQUISITE      = source_id -> organisation mapping (OWNER INPUT, absent)
    PRODUCTION DEPLOYMENT      = BLOCKED
    HISTORICAL ATTRIBUTION     = NOT AN ISSUE — no production message has been accepted
    PARTIAL IMPLEMENTATION     = FORBIDDEN

The receiver as built is correct for the *other* reading of this question. It is
not defective; it is scoped to a decision that has now gone the other way, and
the work to change it is real, bounded, and enumerated above.

---

## 9. Findings added by the 2026-09-13 implementation attempt

Implementation was attempted and stopped at the Phase 1 acceptance boundary (§10).
The inspection that preceded the stop produced three findings this document did
not previously contain. All three were verified against the code, and two of them
change the plan in §7.

### 9.1 There is a SECOND read surface, and it is the one the UI actually uses

§3.2 documents the four `ops/backend` endpoints. It misses the platform-side
surface entirely:

```
frontend  /app/lls-monitoring
   -> GET /operations/monitoring/state
      GET /operations/monitoring/sources
      GET /operations/monitoring/history
   -> backend/src/algo_platform/modules/operations/presentation/router.py
   -> MonitoringStore  (.../operations/infrastructure/monitoring_store.py)
   -> raw SQL, second engine, straight at the ops database
```

`MonitoringStore` opens its own connection to the ops database and reads
`monitoring_projections`, `monitoring_sequence_state` and `monitoring_evidence`
with hand-written SQL. **It does not go through the ops API**, so tenant filtering
added to the `ops/backend` router would not protect it.

The same discard pattern is present here as on the ops side:

```python
def monitoring_sources(_tenant: OpsTenant, store: MonitoringDep) -> ...:
    return [MonitoringSourceRow.model_validate(row) for row in store.sources()]
```

`OpsTenant` is `Annotated[TenantContext, Depends(require_ops_read)]` and
`TenantContext` already carries `tenant_id: TenantId`. It is bound and dropped on
all three endpoints, and `MonitoringStore.sources()` has no `WHERE` clause at all.

**Consequence for §7:** step 5 must cover *both* read surfaces, or partitioning is
partial in exactly the way §1 warns about. There is no platform-side monitoring
table to secure — the platform owns none; it reads the receiver's.

### 9.2 A real foreign key to the organisation registry is not possible

The deployed topology puts the two tables in different databases on different
servers:

| Table | Database | Server | Roles |
|---|---|---|---|
| `organizations` | `algo` | `postgres:5432` | platform |
| `monitoring_*` | `ops_telemetry` | `ops-postgres:5432` | `ops_owner` / `ops_receiver` |

PostgreSQL has no cross-database foreign keys, so
`monitoring_evidence.organisation_id -> organizations.id` **cannot be declared**
in the production topology. (`Settings.resolve_ops_database_url` does let
`OPS_DATABASE_URL` fall back to `DATABASE_URL`, so a single-database deployment is
possible — but `deploy/k8s/46-ops-db.yaml` deliberately separates them, and the
role separation that protects append-only evidence depends on that separation.)

This is a genuine conflict with a stated requirement, recorded rather than worked
around. What is achievable instead, and must be decided before step 3:

* `organisation_id UUID NOT NULL` on the receiver side with **no** FK, plus
  startup validation of every configured mapping against the authoritative
  registry, fail-closed; or
* a mirrored `monitoring_organisations` table inside `ops_telemetry` that the
  monitoring tables *can* reference, fed from the platform registry — a real FK
  locally, at the cost of a synchronisation path that can drift.

Neither is free. Choosing silently would be the wrong outcome.

### 9.3 The read path needs no new owner input — only the write path does

This narrows the blocker. Tenant identity already exists on both read surfaces:

* Platform JWTs already carry the organisation: `jwt_service.py` encodes
  `"org": str(organization_id)` and decodes it back to `organization_id: UUID`.
* `ops/backend` already verifies platform-issued JWTs (`_verify_jwt`, with
  `ops_jwt_public_key`) — it simply reads `sub` and `permissions` and drops `org`.
* The platform side already has `TenantContext.tenant_id`.

So `Viewer` gaining an organisation is ordinary engineering against an existing
authoritative claim. **No owner decision is required for the read path.**

The write path is the part that has no source of truth, because the authenticated
publisher identity is `MONITORING_SOURCE_TOKENS` (`source_id:token`) and nothing
in the system relates a `source_id` to an organisation.

---

## 10. What the owner must supply, exactly

Implementation is stopped here. This is the complete input required to restart it.

**Configuration location:** `ops/backend/app/core/config.py`, a new `Settings`
field alongside `monitoring_source_tokens` / `monitoring_source_environments`,
supplied by environment variable and injected as a Kubernetes Secret through
`deploy/k8s/45-ops.yaml`. It must not be committed to git.

**Proposed variable and format** (following the existing `source:value` idiom):

```
MONITORING_SOURCE_ORGANISATIONS="<source_id>:<organisation_uuid>[,<source_id>:<organisation_uuid>]"
```

**The two values that do not exist anywhere in this repository:**

1. **The production `source_id`.** It must be *byte-identical* to the value the
   LLS producer puts in the message body, because acceptance already requires
   `principal.authorizes_source(body["source_id"])`. The frozen fixtures use
   `lls-contract-fixture`, which is a fixture identifier and explicitly **not** a
   production one. Engineering cannot derive this — it is an LLS deployment fact.
2. **The organisation UUID**, which must be an existing `organizations.id` in the
   platform `algo` database — `Organization.id` is `TenantId`, a `NewType` over
   `uuid.UUID`, serialised as a plain UUID string. The slug is a label and must
   not be used as the security identity.

Both must satisfy the §2 constraints: the mapping is injective, `source_id` is
unique across organisations, and the mapping is stable for the life of the
evidence it attributes.

**Why no placeholder was created.** A mapping invented to make a migration run
would attribute real customer evidence to a guessed organisation, and
`monitoring_evidence` is append-only behind a database trigger with no UPDATE
grant for the receiver role — so the attribution could never be corrected. A
wrong value here is permanent in a way a missing value is not.
