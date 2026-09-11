# monitoring.v1 — canonical wire contract

**This is the authoritative wire contract between LLS and algomatric.in.**
It is owned by the LLS producer. Algomatric is the receiver.

## Do not edit these files

`monitoring.v1.schema.json` and `ALGOMATRIC_MONITORING_CONTRACT.md` are copied
**verbatim** from the LLS handoff package. Editing them here would create a
second contract that silently diverges from the producer — the exact failure
this directory exists to prevent.

If the receiver cannot satisfy something in this schema, that is a receiver
defect or a contract conversation with LLS. It is never a reason to edit these
files.

## Source

| | |
|---|---|
| LLS repository path | `docs/black_box/implementation/algomatric_contract_fixture_package/` |
| Copied | 2026-09-11 |
| `monitoring.v1.schema.json` | sha256 `f94023bc1a541b13dd710bff367bcf2a1cc4b47eeeb1248014707f1c9ce262f4` |
| `ALGOMATRIC_MONITORING_CONTRACT.md` | sha256 `e51fc7b4950a3525089f9a50e47e34774e610e09f810845a015d9ebd5d2cb224` |

The full handoff package — including the fixtures the receiver is tested
against — is vendored at [`tests/fixtures/lls-monitoring-v1-handoff/`](../../tests/fixtures/lls-monitoring-v1-handoff).
`tests/test_monitoring_v1_contract.py` asserts these two files are byte-identical
to their copies in that package, so a re-sync that changes one and not the other
fails the build.

## Resyncing

When LLS publishes a new package:

1. Copy the package to `tests/fixtures/lls-monitoring-v1-handoff/`.
2. Copy `schema/monitoring.v1.schema.json` and
   `contract/ALGOMATRIC_MONITORING_CONTRACT.md` here.
3. Update the hashes above.
4. Run the contract suite. Every difference it reports is a receiver change to
   make, not a schema change to make.

## Normative limits (from the schema `$comment` and the contract document)

These are not expressible in JSON Schema and are enforced by
`app/monitoring/contract.py`:

| Limit | Value |
|---|---|
| Request size | 1 MiB (1,048,576 UTF-8 bytes) |
| Array elements | 100 per array |
| Nesting depth | 24 |
| Total nodes | 30,000 |
| String length | 4,096 characters |
| Duplicate object keys | rejected |
| Non-finite numbers | rejected |

`message_id` is `mon1/` + SHA-256 of the canonical JSON of the message **with
`message_id` removed** — a content address, and independently verifiable by the
receiver.

The request digest carried in `X-Monitoring-SHA256` is SHA-256 over the **whole
request body bytes**, not over any sub-object.

## What was superseded

`schemas/monitoring-export/v1/` was a receiver-side proposal written before the
LLS producer contract was available. It is not a wire contract and is retained
only as history at
[`docs/monitoring/superseded/monitoring-export-v1-proposal/`](../../docs/monitoring/superseded/monitoring-export-v1-proposal).
Nothing loads it.
