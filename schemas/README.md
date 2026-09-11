# Published schemas

External contracts. Everything here is consumed across a system boundary, so
treat each directory as a published artefact rather than as source.

```
schemas/
└── monitoring-v1/          the LLS ↔ algomatric.in wire contract
    ├── monitoring.v1.schema.json        owned by LLS — do not edit
    ├── ALGOMATRIC_MONITORING_CONTRACT.md  owned by LLS — do not edit
    └── PROVENANCE.md                    source, hashes, resync procedure
```

## monitoring.v1 is owned by the producer

LLS defines the contract; algomatric.in receives against it. The two files above
are copied **verbatim** from the LLS handoff package and are hash-checked by
`ops/backend/tests/test_monitoring_v1_contract.py` on every run. If the receiver
cannot satisfy something in the schema, that is a receiver defect or a
conversation with LLS — never a reason to edit the schema here.

Start with [`PROVENANCE.md`](monitoring-v1/PROVENANCE.md) for the normative
limits that JSON Schema cannot express, and with
[`docs/monitoring/LLS_CONTRACT_RECONCILIATION.md`](../docs/monitoring/LLS_CONTRACT_RECONCILIATION.md)
for what the receiver currently implements.

## The rule that catches people out

A fact the producer cannot determine is sent explicitly, with the value present
and null:

```json
{"value": null, "status": "UNKNOWN", "reason": "not_available"}
```

Preserve it exactly. `UNKNOWN`, `UNSUPPORTED`, `N/A`, `STALE`, `INCOMPLETE`,
`UNTRUSTED`, `SIMULATED` and `SYNTHETIC_CLOCK` are distinct and must never
become `false`, `0`, `healthy` or `flat`. An unfamiliar enum value is not
permission to assume health.

## Fixtures

The producer's fixture package — 22 messages, 11 HTTP cases, ACK fixtures and a
manifest — is vendored at
[`tests/fixtures/lls-monitoring-v1-handoff/`](../tests/fixtures/lls-monitoring-v1-handoff)
and is the authoritative test artefact. Do not hand-write equivalents.

```bash
cd ops/backend && .venv/Scripts/python.exe -m pytest tests/test_monitoring_v1_contract.py -q
```

## Superseded

`monitoring-export/v1` was a receiver-side proposal predating the producer
contract. It is not a wire contract and is retained only as history at
[`docs/monitoring/superseded/monitoring-export-v1-proposal/`](../docs/monitoring/superseded/monitoring-export-v1-proposal).
Nothing loads it, and a test asserts `schemas/` holds exactly one contract
directory so it cannot quietly return.
