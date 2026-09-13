# monitoring.v1 — owner decision sheet

    STATUS: ALL FOUR DECISIONS RECORDED
    Decided by: the authorised project owner
    Decision date: 2026-09-13
    Recorded by: engineering, from the owner's explicit selection

None of these was chosen by engineering. Each was selected by the owner, and the
selections are transcribed below exactly as given.

Every option below is a **decision example, not a recommendation**. Nothing is
approved unless the owner selects it. Where a figure is `UNKNOWN` it is left
`UNKNOWN` — no blank is filled with a plausible-sounding number.

| # | Decision | Blocks | Deferrable? |
|---|---|---|---|
| 1 | Accepted-evidence retention | Production deployment | Partly — decision 2 can be answered alone |
| 2 | Rejected-traffic retention | Production deployment | No — this is the unbounded one |
| 3 | Monitoring tenancy | Production deployment | No — partly irreversible once traffic is accepted |
| 4 | Production publisher count | Volume sizing, and decision 1 | No |

---

## DECISION 1 — Accepted evidence retention

**How long must accepted monitoring evidence remain directly queryable?**

    [ ] 30 days
    [ ] 90 days
    [ ] 1 year
    [ ] 3 years
    [ ] 7 years
    [x] indefinite          <-- SELECTED 2026-09-13
    [ ] other: ______________

**DECIDED: evidence is retained indefinitely.** Nothing deletes accepted
evidence, and nothing may be added that does. The append-only trigger
(`c7f41a92d8e5`) stays, role separation stays, and no TTL, cron, cascade or
archive job may touch `monitoring_evidence`.

Engineering consequence: **no code change, no migration, no trigger change.**
This is the option that requires the least work and preserves the forensic
record in full.

### What each costs

`monitoring_evidence` is append-only and **nothing deletes anything today**.
That is deliberate — evidence deletion was made a reviewed act rather than a
configuration flag, enforced by a row-level trigger (migration `c7f41a92d8e5`)
and by role separation.

Storage for **one publisher** at the contract maximum rate, nothing deleted
(DERIVED from MEASURED bytes; see `PRODUCTION_CAPACITY_MODEL.md` §8 for other
publisher counts):

| Horizon | Scenario A (projections bounded) | Scenario B (projections 1:1) |
|---|---|---|
| 1 year | 18.2 GB | 31.2 GB |
| 3 years | 54.6 GB | 93.7 GB |
| 7 years | 127.4 GB | 218.6 GB |

The provisioned 100Gi volume (107.0 GB usable) therefore holds **one** publisher
for 5.9 years under Scenario A, 3.4 years under Scenario B.

### What engineering does for each answer

| Answer | Engineering consequence |
|---|---|
| **Indefinite** | A scheduled job for rejected traffic only. **No migration, no trigger change.** |
| **A fixed period, archived** | New archive path, a reviewed migration to permit deletion, **and a decision about what `rebuild()` means** — it currently replays *all* evidence. |
| **A fixed period, deleted** | As above, plus the append-only trigger must be dropped in a reviewed migration. **Irreversible: deleted evidence cannot explain a past trading outcome.** |

### Three things to weigh

* **"Indefinite" is genuinely viable at one publisher** and was not before this
  phase: the publication rate turned out to be a contract fact, so it is a
  bounded commitment rather than an open one. It stops being cheap at around two
  to three publishers (decision 4).
* **Any period-based option changes what `rebuild()` means.** Projections are
  rebuilt by replaying all evidence. Remove evidence and a rebuild no longer
  reconstructs the same state. Decide it *with* the policy, not after the first
  archive run.
* **Legal or compliance retention obligations are UNKNOWN to engineering.** If
  monitoring evidence is ever used to explain a trading outcome to anyone
  outside the team, its retention may be governed by rules nobody on this side
  has stated. This document cannot infer them and does not try.

---

## DECISION 2 — Rejected traffic retention

**What retention applies to quarantine rows and stored raw request bodies?**

    [x] 30 days             <-- SELECTED 2026-09-13
    [ ] 60 days
    [ ] 90 days
    [ ] other: ______________

**DECIDED: quarantine rows and stored raw rejected request bodies are retained
for 30 days.** This closes the only unbounded growth path an authenticated
publisher could drive deliberately.

Scope, stated precisely so it cannot widen by accident:

* **In scope:** `monitoring_quarantine`, `monitoring_raw_requests`.
* **Explicitly NOT in scope:** `monitoring_evidence` (decision 1: indefinite),
  `monitoring_audit` (the security record of *every* attempt, accepted and
  rejected alike — it is not "rejected traffic"), `monitoring_projections`,
  `monitoring_sequence_state`.

This is the separable one, and the one that should not ship unanswered:

* Diagnostic value is measured in days to weeks. Nobody investigates a malformed
  request from last year.
* These are the tables a holder of a valid publisher credential could otherwise
  grow deliberately.
* Answering this alone closes the unbounded-growth concern for the tables that
  warrant it, and needs **no migration and no trigger change**.

The only wrong answer is the current one, which is "forever".

---

## DECISION 3 — Monitoring tenancy

**Is monitoring data operator telemetry, or customer data?**

    [ ] infrastructure / operator-wide
    [x] organisation / customer-partitioned    <-- SELECTED 2026-09-13

**DECIDED: monitoring data is customer data and must be partitioned by
organisation.**

    CONSEQUENCE: PRODUCTION DEPLOYMENT IS BLOCKED.

The current build scopes monitoring by deployment tier, not by organisation.
That is not a defect — it is the other reading of this question — but it is the
wrong one under this decision. The organisation dimension is **unbuilt
engineering work**.

No production monitoring message may be accepted until the complete boundary is
implemented and tested, because evidence is append-only: a message accepted
without organisation attribution can never be given one.

Partial partitioning must not be implemented. See
`TENANCY_IMPACT_ASSESSMENT.md`.

### What is actually true today

Monitoring data is scoped by **deployment tier**, never by organisation. Every
organisation with a `TRADING_VIEW` member sees the same monitoring data.

**This is not a defect.** Tenancy is enforced correctly everywhere it is
declared — a foreign organisation receives 403, MEASURED across 8 checks through
real JWT, session and membership. The question is what the data *is*, and only
the owner can answer that.

| Option | Reading | Consequence |
|---|---|---|
| **Operator-wide** | Monitoring describes *our* infrastructure. Any staff member with `TRADING_VIEW` may see it. | **No code change.** Current behaviour is correct as built. Document the intent so the next reader does not "fix" it. |
| **Customer-partitioned** | Monitoring describes a customer's trading system and belongs to that customer. | **Code change required before production.** Evidence, projections and the read path all need an organisation dimension. |

### Why this cannot be deferred

Evidence is append-only by design. Messages accepted before the decision carry
no organisation attribution and **cannot be given one later** — not by
engineering choice, but because the trigger and the role separation exist
precisely to prevent rewriting history.

Choosing operator-wide and later switching costs a permanent, unattributable
segment of the evidence record. Choosing partitioned first costs work now and
nothing later. That asymmetry is why this is on the critical path.

---

## DECISION 4 — Production publisher count

**How many LLS monitoring services will publish to this receiver?**

    Number of publishers: 1          <-- SELECTED 2026-09-13

**DECIDED: one LLS monitoring service publishes to this receiver.**

Not inferred, and not guessable from anything available here. The **per-service**
rate is settled and needs no owner input — one delivery per service cycle,
minimum cycle 10 s, single-flight, a maximum of **0.1 msg/s**, CONTRACT. What is
UNKNOWN is how many such services exist.

### Consequences, computed not estimated

`python -m scripts.monitoring_capacity_table` from `ops/backend` reproduces this.

| Publishers | Demand vs MEASURED 32.7 msg/s | 100Gi lasts (Scenario A) | 100Gi lasts (Scenario B) |
|---|---|---|---|
| 1 | 0.31% — 327x headroom | 5.88 yr | 3.43 yr |
| 5 | 1.53% — 65x headroom | **1.18 yr** | **0.69 yr** |
| 10 | 3.06% — 33x headroom | 0.59 yr | 0.34 yr |
| 25 | 7.65% — 13x headroom | 0.24 yr | 0.14 yr |
| 50 | 15.29% — 7x headroom | 0.12 yr | 0.07 yr |
| 100 | 30.58% — 3x headroom | 0.06 yr | 0.03 yr |

### The finding that matters

**Storage binds long before throughput.** Demand does not reach the measured
single-worker throughput until **327 publishers** — but the provisioned volume
falls below one year of capacity at **6 publishers** (Scenario A) or **4**
(Scenario B).

So the 327× headroom figure, while accurate, answers the wrong question. The
constraint is disk, and it arrives early.

This also couples decision 4 to decision 1: at one publisher, "keep everything
forever" is comfortable for years. At ten it is a seven-month commitment. **The
retention decision cannot be made sensibly without this number.**

---

## Not an owner decision, but worth asking the producer

`capture_ref` is part of the projection key, and whether it changes between
service cycles decides Scenario A versus Scenario B — a **1.73×** difference in
storage per message. The canonical contract does not establish it, and every
producer fixture uses one stable value.

The question for the producer's owner is narrow: **does `capture_ref` change
between service cycles?** That is a contract clarification, not an LLS change,
and LLS must not be modified to answer it.

---

## Summary

| # | Question | Decision | Recorded | Engineering required |
|---|---|---|---|---|
| 1 | Accepted evidence retention | **Indefinite** | 2026-09-13 | **None** — nothing deletes evidence, and nothing may be added that does |
| 2 | Rejected traffic retention | **30 days** | 2026-09-13 | A bounded scheduled cleanup, quarantine + raw requests only |
| 3 | Monitoring tenancy | **Organisation-partitioned** | 2026-09-13 | **Substantial and unbuilt — blocks production** |
| 4 | Production publisher count | **1** | 2026-09-13 | None — sets capacity, which is comfortable at this count |
| — | `capture_ref` lifecycle (producer clarification) | **still OPEN** | — | None. Changes storage by 1.73x; not a blocker at one publisher |

### The gate after these decisions

    PRODUCTION DEPLOYMENT REMAINS BLOCKED

Decisions 1, 2 and 4 are closed and cheap. **Decision 3 is what blocks
production**, and it does so by the owner's own choice rather than by any defect:
organisation partitioning does not exist in this build, and evidence is
append-only, so it cannot be retrofitted onto messages accepted without it.

One further owner input is now **required by decision 3 and does not yet exist**:
a mapping from each publisher `source_id` to the organisation that owns its data.
The monitoring.v1 contract carries no organisation field — the producer does not
send one, and LLS must not be changed to add one — so the mapping is receiver-side
configuration that only the owner can supply. See
`TENANCY_IMPACT_ASSESSMENT.md` §2.
