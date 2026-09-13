"""Reproduce the monitoring.v1 capacity tables in docs/monitoring/PRODUCTION_CAPACITY_MODEL.md.

The tables in that document must never be hand-edited: run this and paste, so a
changed input cannot leave a stale number behind. Every constant below carries
its provenance.

Two things this script deliberately does NOT decide:

* **Publisher count** is an owner input. A row is printed per candidate so the
  consequence of each is visible; none is recommended.
* **Projection growth** depends on how ``capture_ref`` behaves in production,
  which the canonical contract does not establish. Both scenarios are printed
  side by side; neither is chosen.

    python -m scripts.monitoring_capacity_table
"""

from __future__ import annotations

# --- CONTRACT: schemas/monitoring-v1/ALGOMATRIC_MONITORING_CONTRACT.md -------
# "One oldest pending delivery attempt per service cycle; the default cycle
# interval is 30 seconds and minimum is 10." A scoped delivery-owner lock
# serialises attempts per source instance, so a publisher is single-flight and
# cannot burst above its cycle rate.
MAX_RATE_PER_PUBLISHER = 1 / 10
DEFAULT_RATE_PER_PUBLISHER = 1 / 30

# --- MEASURED: docs/monitoring/PERFORMANCE_BASELINE.md §2 and §7 ------------
THROUGHPUT_ONE_WORKER = 32.7  # msg/s, 1 publisher, 1 worker, concurrency matrix
THROUGHPUT_SUSTAINED = 86.3  # msg/s, mean over the 4.17h single-worker run

# --- MEASURED: PERFORMANCE_BASELINE.md §8, n = 750,400 ----------------------
# Large-n figures. They supersede the n=3,200 and n=120 measurements, in which
# fixed page and index costs had not yet amortised away.
EVIDENCE_BYTES = 5_505
AUDIT_BYTES = 269
PROJECTION_ROW_BYTES = 4_128

#: MEASURED steady-state WAL on disk: 23 segments x 16 MB. WAL is recycled, so
#: this is a fixed floor rather than per-message growth. Archiving or PITR would
#: change that, and neither was measured.
WAL_FLOOR_BYTES = 368 * 1024**2

# Provisioned in deploy/k8s/46-ops-db.yaml.
PVC_GIB = 100

SECONDS_PER_DAY = 86_400
SECONDS_PER_YEAR = 365 * SECONDS_PER_DAY
GB = 1_000_000_000

#: Candidate production publisher counts. Which applies is UNKNOWN — owner input.
PUBLISHER_COUNTS = (1, 5, 10, 25, 50, 100)

#: Per-message database cost under each reading of the contract.
#:
#: A projection is keyed by
#: (receiver_deployment_environment, source_id, message_type, capture_ref).
#: MEASURED both ways over ~370,000 messages each: with a stable capture_ref one
#: projection row served 379,200 messages; with a per-message capture_ref the
#: table grew 1:1. The contract does not say which production does.
SCENARIO_A = EVIDENCE_BYTES + AUDIT_BYTES  # projections bounded
SCENARIO_B = EVIDENCE_BYTES + AUDIT_BYTES + PROJECTION_ROW_BYTES  # projections 1:1


def gb_per_year(rate: float, bytes_per_message: int) -> float:
    """Growth with nothing deleted — there is no approved retention policy."""
    return rate * SECONDS_PER_YEAR * bytes_per_message / GB


def rule(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


def main() -> None:
    pvc_gb = PVC_GIB * 1024**3 / GB

    rule("Inputs")
    print(f"  CONTRACT  max rate per publisher      {MAX_RATE_PER_PUBLISHER:.3f} msg/s "
          f"(10 s cycle floor, single-flight)")
    print(f"  CONTRACT  default rate per publisher  {DEFAULT_RATE_PER_PUBLISHER:.4f} msg/s")
    print(f"  MEASURED  receiver, 1 worker          {THROUGHPUT_ONE_WORKER} msg/s "
          f"(matrix) / {THROUGHPUT_SUSTAINED} msg/s (4.17h mean)")
    print(f"  MEASURED  evidence                    {EVIDENCE_BYTES:,} B/message")
    print(f"  MEASURED  audit                       {AUDIT_BYTES:,} B/message")
    print(f"  MEASURED  projection row              {PROJECTION_ROW_BYTES:,} B/row")
    print(f"  DERIVED   Scenario A per message      {SCENARIO_A:,} B  (projections bounded)")
    print(f"  DERIVED   Scenario B per message      {SCENARIO_B:,} B  (projections 1:1)")
    print(f"  MEASURED  WAL floor                   {WAL_FLOOR_BYTES/GB:.3f} GB "
          "(recycled, not growth)")
    print("  UNKNOWN   publisher count, production message mix, capture_ref lifecycle")
    print("  NOT MEASURED  backups, WAL archiving, PITR, replication")

    rule("Throughput — demand against the MEASURED receiver")
    print("| Publishers | Demand at contract max | Messages/day | Messages/year | "
          "% of 32.7 msg/s | Headroom |")
    print("|---|---|---|---|---|---|")
    for n in PUBLISHER_COUNTS:
        demand = n * MAX_RATE_PER_PUBLISHER
        print(f"| {n} | {demand:.1f} msg/s | {round(demand * SECONDS_PER_DAY):,} | "
              f"{round(demand * SECONDS_PER_YEAR):,} | "
              f"{100 * demand / THROUGHPUT_ONE_WORKER:.2f}% | "
              f"{THROUGHPUT_ONE_WORKER / demand:.0f}x |")

    rule("Storage GB/year at the contract MAXIMUM rate, nothing deleted")
    print("| Publishers | Evidence | Audit | Scenario A total | Projections (B) | "
          "Scenario B total |")
    print("|---|---|---|---|---|---|")
    for n in PUBLISHER_COUNTS:
        d = n * MAX_RATE_PER_PUBLISHER
        print(f"| {n} | {gb_per_year(d, EVIDENCE_BYTES):,.1f} | "
              f"{gb_per_year(d, AUDIT_BYTES):,.1f} | "
              f"**{gb_per_year(d, SCENARIO_A):,.1f}** | "
              f"{gb_per_year(d, PROJECTION_ROW_BYTES):,.1f} | "
              f"**{gb_per_year(d, SCENARIO_B):,.1f}** |")

    rule("Storage GB/year at the contract DEFAULT rate (30 s cycle)")
    print("| Publishers | Scenario A total | Scenario B total |")
    print("|---|---|---|")
    for n in PUBLISHER_COUNTS:
        d = n * DEFAULT_RATE_PER_PUBLISHER
        print(f"| {n} | {gb_per_year(d, SCENARIO_A):,.1f} | "
              f"{gb_per_year(d, SCENARIO_B):,.1f} |")

    rule(f"How long the provisioned {PVC_GIB}Gi ({pvc_gb:.1f} GB) volume lasts")
    usable = pvc_gb - WAL_FLOOR_BYTES / GB
    print(f"  Usable after the MEASURED WAL floor ({WAL_FLOOR_BYTES/GB:.3f} GB): "
          f"{usable:.1f} GB. Backups and archiving are NOT MEASURED and are not")
    print("  subtracted here, so these are upper bounds on the time available.")
    print()
    print("| Publishers | Scenario A, max rate | Scenario B, max rate | "
          "Scenario A, default rate |")
    print("|---|---|---|---|")
    for n in PUBLISHER_COUNTS:
        d = n * MAX_RATE_PER_PUBLISHER
        dd = n * DEFAULT_RATE_PER_PUBLISHER
        print(f"| {n} | {usable / gb_per_year(d, SCENARIO_A):.2f} yr | "
              f"{usable / gb_per_year(d, SCENARIO_B):.2f} yr | "
              f"{usable / gb_per_year(dd, SCENARIO_A):.2f} yr |")

    rule("Where each limit binds")
    print(f"  Throughput reaches the MEASURED single-worker figure at "
          f"{THROUGHPUT_ONE_WORKER / MAX_RATE_PER_PUBLISHER:.0f} publishers.")
    for label, cost in (("A", SCENARIO_A), ("B", SCENARIO_B)):
        one_year = usable / gb_per_year(MAX_RATE_PER_PUBLISHER, cost)
        print(f"  Scenario {label}: the provisioned volume holds one publisher for "
              f"{one_year:.1f} years at the contract maximum;")
        n_one_year = usable / gb_per_year(MAX_RATE_PER_PUBLISHER, cost)
        print(f"              it falls below 1 year at "
              f"{int(n_one_year) + 1 if n_one_year > 1 else 1} publishers.")
    print("\n  Storage binds far earlier than throughput in both scenarios.")
    print("\n  UNKNOWN and not inferred here: publisher count, production message mix,")
    print("  capture_ref lifecycle, retention period, backup policy.")


if __name__ == "__main__":
    main()
