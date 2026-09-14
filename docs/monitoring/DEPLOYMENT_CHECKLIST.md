# monitoring.v1 — production deployment checklist

**Nothing in this document has been executed.** No production infrastructure,
DNS, credential, database, broker or trading path was touched by this phase.
This is the procedure to follow *when* the gate opens — not a record of a
deployment.

The gate is **closed** until the four questions in [OWNER_DECISIONS.md](OWNER_DECISIONS.md)
are answered. Section 0 exists to stop this checklist being started before then.

Order matters. Several steps are irreversible in a specific sense:
`monitoring_evidence` is append-only, so a message accepted under the wrong
configuration cannot be corrected, only annotated.

---

## 0. Gate — owner decisions

All four were recorded on **2026-09-13**. Three are closed. One blocks.

- [x] **0.1 Accepted-evidence retention — INDEFINITE.** No deletion, no TTL, no
      archive job. The append-only trigger and role separation stay. Nothing to
      implement. Recorded in `RETENTION_POLICY.md`.
- [x] **0.2 Rejected-traffic retention — 30 DAYS.** Quarantine and raw rejected
      bodies only. Implemented in `retention_service.py`; asserted in production
      configuration as `MONITORING_REJECTED_RETENTION_DAYS: "30"`. Never touches
      evidence or audit.
- [ ] **0.3 Monitoring tenancy — ORGANISATION-PARTITIONED. → BLOCKS PRODUCTION.**
      The organisation dimension does not exist in this build. It is unbuilt
      engineering work, and it has its own blocking prerequisite: a
      `source_id → organisation` mapping that only the owner can supply. **Do
      not proceed past this line.** See `TENANCY_IMPACT_ASSESSMENT.md`.
- [x] **0.4 Publisher count — 1.** Capacity is comfortable: 0.31% of measured
      single-worker throughput, and 3.4–5.9 years of volume depending on the
      `capture_ref` question.

> **STOP.** Gate 0.3 is open by the owner's own decision. No production
> monitoring message may be accepted until organisation partitioning is
> implemented in full and tested, because evidence is append-only and a message
> accepted without attribution can never be given one.
>
> Sections 1–5 below remain correct and are what to work through **after** 0.3
> closes. They must not be started as a way of making progress while it is open.

## 1. Pre-deployment

### Image and contract

- [ ] **1.1 Image contains the canonical schema.** The receiver refuses every
      message it cannot validate, and `/api/health` — which the probes use —
      does **not** consult the contract, so a missing schema is otherwise
      silent.

      ```bash
      docker run --rm --entrypoint sh <image> -c 'ls -l /app/schemas/monitoring-v1'
      ```

- [ ] **1.2 Schema byte-identical to the producer's published copy.**
      `message_id` is a content address over canonical JSON and the request
      digest covers exact bytes, so a rewritten schema file is a broken
      receiver, not a cosmetic difference.

      ```bash
      docker run --rm --entrypoint sh <image> -c \
        'sha256sum /app/schemas/monitoring-v1/monitoring.v1.schema.json'
      ```

      Compare against the producer's copy **at deploy time**. It was
      `f94023bc1a541b13dd710bff367bcf2a1cc4b47eeeb1248014707f1c9ce262f4` when
      MEASURED in this review; that is a record, not a permanent constant.

- [ ] **1.3 Startup guard refuses a half-configured deployment.** Confirm the
      image will not boot with publisher credentials but no deployment tier.
      This is the failure mode the guard exists for.
- [ ] **1.4 Migration image tag** on the `ops-migrate` initContainer matches the
      application container tag.

### Database

- [ ] **1.5 Create the roles** (operator, once, as the instance superuser).
      Passwords from the secret manager — never typed into a file or shell
      history.

      ```sql
      CREATE ROLE ops_owner    LOGIN PASSWORD '<owner-password>';
      CREATE ROLE ops_receiver LOGIN PASSWORD '<receiver-password>';
      ALTER DATABASE ops_telemetry OWNER TO ops_owner;
      REVOKE CONNECT ON DATABASE ops_telemetry FROM PUBLIC;
      GRANT  CONNECT ON DATABASE ops_telemetry TO ops_owner, ops_receiver;
      ```

- [ ] **1.6 `REVOKE CONNECT ... FROM PUBLIC` confirmed applied.** Verify
      explicitly; it is easy to omit and silently leaves the database reachable
      by every role.
- [ ] **1.7 PostgreSQL logging.** An INSERT into `monitoring_evidence` carries
      the whole message as a bound parameter, so raised logging copies message
      bodies into the database log — which has different retention and access
      control from the evidence table.

      ```sql
      SHOW log_statement;                        -- expect: none  (or ddl)
      SHOW log_parameter_max_length_on_error;    -- expect: 0
      ```

      Anything other than `none` or `ddl` requires explicit owner approval.

- [ ] **1.8 Backup policy defined.** **NOT MEASURED** by this review. The
      capacity model in 1.9 covers database growth only; backups, WAL archiving,
      PITR and replication are additional and unquantified here.
- [ ] **1.9 Volume sized for the decided publisher count — 1.** The provisioned
      100Gi (107.0 GB usable) gives 5.88 years under Scenario A, 3.43 years
      under Scenario B. See `PRODUCTION_CAPACITY_MODEL.md` §9.

      **Indefinite retention on a finite volume means the volume fills.** That
      is the consequence of owner decision 1, not a contradiction of it. Record
      an operational calendar item to expand storage before ~year 3.4, and make
      the storage alert (3.17) fire on *projected exhaustion*, not on a raw
      percentage — with indefinite retention, usage never stops rising.

### Transport

- [ ] **1.10 TLS certificate valid** for the production hostname, from a CA the
      producer trusts.
- [ ] **1.11 Hostname validation enforced** end to end. The receiver does not
      terminate TLS in production; the edge does.
- [ ] **1.12 No TLS downgrade path.** Plain HTTP must not reach the receiver,
      and must not redirect to HTTPS in a way that would let a credential travel
      in clear text first.
- [ ] **1.13 `X-Forwarded-Proto` set correctly by the edge proxy**, and trusted
      only from the edge.
- [ ] **1.14 Redirect handling.** The receiver follows no redirects. The
      trailing-slash behaviour documented in `TLS_VALIDATION.md` §4 is an
      invariant — do not "tidy" it away.

### Runtime

- [ ] **1.15 Secrets injected** from the secret manager. **Nothing** may be
      committed with a real value, and no credential may appear in source,
      fixtures, documentation, logs, the frontend or test output.
      - `ops-migration-secrets.DATABASE_URL` → the **owner** role
      - `ops-secrets.DATABASE_URL` → the **non-owning receiver** role
      - `MONITORING_SOURCE_TOKENS` → `source_id:token` per LLS source; the
        `source_id` must match the producer's exactly
      - `MONITORING_ADMIN_TOKEN` → distinct from every publisher token
      - `MONITORING_DEPLOYMENT_ENVIRONMENT` → this receiver's tier
        (`production`). **Not** the producer's environment
- [ ] **1.16 Memory limit.** 512Mi, against a MEASURED single-worker peak of
      127.5 MiB over 4.17 h / 746,400 messages (~4.0× headroom). Linux and
      container memory accounting are **NOT TESTED**; the margin is headroom
      against that, not padding. See `PERFORMANCE_BASELINE.md` §7.
- [ ] **1.17 CPU limit** 500m, request 100m. Contract demand is 0.1 msg/s per
      publisher against a MEASURED 32.7 msg/s single worker.
- [ ] **1.18 Restart policy** and `terminationGracePeriodSeconds` reviewed.
- [ ] **1.19 Liveness and readiness probes** configured. Note that `/api/health`
      does **not** consult the contract — see 2.8.
- [ ] **1.20 Alerting configured** for the conditions in section 4.

---

## 2. Deployment

- [ ] **2.1 Deploy with `MONITORING_SOURCE_TOKENS` empty.** The ingress is then
      disabled — every upload refused 401 — which is a coherent safe state, and
      separates "does the service run" from "does ingest work".
- [ ] **2.2 Migrations succeeded.** The initContainer ran as the **owner** and
      exited 0. A failed migration must block the rollout, not half-start the
      API.
- [ ] **2.3 Apply the receiver's grants**, as `ops_owner`, **after** the first
      migration has created the tables:

      ```sql
      GRANT USAGE ON SCHEMA public TO ops_receiver;
      GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ops_receiver;
      REVOKE ALL ON monitoring_evidence FROM ops_receiver;
      GRANT SELECT, INSERT ON monitoring_evidence TO ops_receiver;
      GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ops_receiver;
      ALTER DEFAULT PRIVILEGES FOR ROLE ops_owner IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ops_receiver;
      ```

      The last statement matters on **every future migration**: without it a
      newly created table is unreachable by the application until someone grants
      it by hand. `monitoring_evidence` must be re-revoked if a migration ever
      recreates it.

- [ ] **2.4 Verify the receiver role cannot destroy evidence.** As
      `ops_receiver`, each of these must FAIL:

      ```sql
      DELETE FROM monitoring_evidence WHERE false;   -- expect: refused by trigger
      UPDATE monitoring_evidence SET source_id = source_id;  -- expect: refused
      TRUNCATE monitoring_evidence;                  -- expect: permission denied
      DROP TABLE monitoring_evidence;                -- expect: permission denied
      ALTER TABLE monitoring_evidence DISABLE TRIGGER ALL;   -- expect: permission denied
      ```

      If **any** succeeds, stop and fix the grants before a single message is
      accepted. Evidence written before this point has no protection.

- [ ] **2.5 Verify the receiver role can still do its job.** `SELECT` and
      `INSERT` on `monitoring_evidence`; full DML on the projection, audit,
      quarantine, raw-request and sequence tables.
- [ ] **2.6 TLS verified** from outside the cluster: valid certificate,
      hostname match, no plain-HTTP path.
- [ ] **2.7 Receiver starts** and the pod becomes ready.
- [ ] **2.8 Contract reports available** — `/api/health` is **not** sufficient,
      it never consults the contract:

      ```
      GET /api/monitoring/v1/health
      → contractAvailable: true, databaseReachable: true,
        receiverDeploymentEnvironment: "production"
      ```

- [ ] **2.9 Authenticated read API** returns correctly for an authorised caller,
      and 401/403 for an unauthorised one.
- [ ] **2.10 Frontend** renders the monitoring page against the live read path.
- [ ] **2.11 Producer acceptance harness** run against the production receiver
      with a real credential, on a clean deployment: **11/11, unmodified.**

---

## 3. Post-deployment

- [ ] **3.1 Enable ingest:** set `MONITORING_SOURCE_TOKENS` and roll.
- [ ] **3.2 Deliver the credential to the LLS operator out of band.** LLS is
      frozen; this is a configuration value handed over, not a change to the
      producer.
- [ ] **3.3 First real message accepted.** Confirm one evidence row, one audit
      row and a projection. From this point the deployment-tier value is
      permanent for those rows.
- [ ] **3.4 Duplicate handled correctly** — re-delivery is acknowledged, not
      double-stored.
- [ ] **3.5 Sequence behaviour correct** — a gap is refused 409 and leaves no
      trace.
- [ ] **3.6 UNKNOWN / STALE states render** as the producer asserted them, never
      computed by the receiver.
- [ ] **3.7 No credential in logs.** Check the application log and the database
      log after the first accepted message for token, password or payload
      material.
- [ ] **3.8 Database failure behaviour** observed once deliberately in a
      controlled window: bounded 503, never a false ACK.
- [ ] **3.9 Recovery** confirmed: ingest resumes with no duplicates.
- [ ] **3.10 Storage monitoring** against the figure for the agreed publisher
      count and the provisioned volume.
- [ ] **3.11 Memory monitoring.** Expect a rise to a plateau within roughly the
      first 35,000 messages, then flat. Growth that continues past that is the
      signal worth alerting on.
- [ ] **3.12 Evidence integrity spot-check** — the append-only trigger still
      present and still refusing.
- [ ] **3.13 Projection row count tracked.** If it grows 1:1 with evidence,
      production is Scenario B and the volume horizon is 1.73× shorter than
      Scenario A. This is the observation that resolves the open `capture_ref`
      question.

### Alerting

- [ ] **3.14** `contractAvailable: false` — the receiver is up and refusing
      everything.
- [ ] **3.15** `databaseReachable: false`.
- [ ] **3.16** Quarantine depth rising — the producer is sending something this
      build cannot validate. Investigate; **do not** widen the receiver, and do
      not change LLS.
- [ ] **3.17** Volume utilisation against the capacity model.
- [ ] **3.18** Resident memory above the measured plateau.

---

## 4. Stop conditions

Halt ingest and investigate immediately on any of these:

| Condition | Why it is a stop |
|---|---|
| **A false ACK** — anything acknowledged that was not durably stored | The single guarantee the producer relies on |
| **Evidence mutation or deletion** | The forensic record is the product |
| **Sequence corruption** — out-of-order acceptance, or a gap silently accepted | Ordered acceptance is a contract requirement |
| **Authentication bypass** — any upload accepted without a valid source credential | |
| **TLS failure or downgrade** | Credentials in clear text |
| **Any receiver-to-trading path appearing** | The isolation is the whole safety argument |
| **Any dependency from LLS to Algomatric appearing** | The dependency runs one way only |
| **Storage exhaustion risk** — volume projected to fill before the retention horizon | |
| **Unexplained memory growth** past the measured plateau | |
| **Contract mismatch** — messages this build cannot validate | Quarantine, escalate to the producer's owner, change nothing |

### Safe stop

Clear `MONITORING_SOURCE_TOKENS` and roll. Every upload is then refused 401.

What the producer does then is CONTRACT, not assumption: a 401 is *"retain
blocked delivery; expose error; retry slowly after 900 seconds"*, at most 100
attempts per message, 256 retained outbox messages. On exhaustion it marks
itself degraded, retains its evidence, and requires operator intervention.

The sentence that matters operationally is the contract's own: **"Never
backpressure Core."** Refusing every upload cannot slow or stop trading. That is
what makes this a safe stop — but it also means a prolonged stop is silent on
our side, so pair it with 3.14.

---

## 5. Rollback

- [ ] **5.1 Application rollback is safe.** Redeploy the previous tag. Evidence
      is append-only and migrations are additive.
- [ ] **5.2 Migration rollback is not an operational step.** Alembic downgrade
      was verified in staging for the monitoring revisions, but a downgrade that
      drops the append-only trigger removes a protection while data is live.
      Treat it as a reviewed change.

---

## What this checklist deliberately does not do

* It does not deploy. No step here has been run against production.
* It does not choose a retention policy, a tenancy model, or a publisher count.
* It does not add evidence deletion of any kind — no cron, no TTL, no cascade.
  Evidence deletion stays a reviewed migration, by design.
* It does not modify, instrument, or depend on LLS. The producer is frozen and
  the dependency runs one way only.
