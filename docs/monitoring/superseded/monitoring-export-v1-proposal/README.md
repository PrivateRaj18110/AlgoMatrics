# SUPERSEDED — `monitoring-export/v1` receiver proposal

**This is not a contract. Nothing loads it. Do not implement against it.**

## What it was

A five-file JSON Schema set written in this repository before the LLS producer
contract was available. At the time, the string "LLS" appeared nowhere in the
codebase and there was nothing to conform to, so the receiver's own proposal was
drafted and — on the information then available — designated canonical.

## Why it was retired

On 2026-09-11 the LLS producer published its actual contract and fixture
package. Measured result:

```
LLS producer-valid fixtures accepted by this proposal: 0 / 19
```

The two were independently designed for the same problem: different message
decomposition, different identity scheme, different freshness model, different
`environment` axis, different sequence semantics. Full analysis in
[`../../LLS_CONTRACT_COMPATIBILITY_REPORT.md`](../../LLS_CONTRACT_COMPATIBILITY_REPORT.md).

The canonical contract is now [`schemas/monitoring-v1/`](../../../../schemas/monitoring-v1),
owned by LLS.

## Why it is kept

Two reasons, neither of them "it might come back":

1. It documents the reasoning behind receiver behaviours that survived the
   change — immutable evidence, quarantine distinct from dead-lettering,
   conflict retention, projections rebuildable from evidence.
2. Its qualified-value design was validated against the real producer and found
   to express the same intent more strictly: LLS writes
   `{"status":"UNKNOWN","value":null}` while this proposal made
   `{"state":"UNKNOWN"}` with the value key *absent*. Both prevent the zero
   substitution. That comparison is worth not losing.

The one thing it got exactly right, verified byte-for-byte against a real LLS
fixture, was the canonical JSON encoding — sorted keys, compact separators,
UTF-8, unescaped non-ASCII. That algorithm carried over unchanged.
