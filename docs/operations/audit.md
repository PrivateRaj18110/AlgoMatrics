# Immutable audit platform (Phase 3)

Every significant business event is recorded to an append-only, tamper-evident
audit log. The trail already spanned identity, billing, brokerage, organizations,
risk, and instruments; Phase 3 makes it *immutable and verifiable*.

## Guarantees

1. **Append-only at the database.** Migration `0006` installs a trigger that
   raises on any `UPDATE` or `DELETE` against `audit_log`. Rows can only be
   inserted.
2. **Tamper-evident hash chain.** Each entry stores `prev_hash` (the previous
   entry's `entry_hash`) and its own `entry_hash = SHA256(prev_hash + canonical
   fields)`. Editing, reordering, or deleting any historical entry invalidates
   every later `entry_hash`, which verification detects and pinpoints.
3. **Serialized appends.** Writes take a transaction-scoped Postgres advisory
   lock so exactly one appender computes the "previous" hash at a time, keeping
   the chain consistent under concurrency. Audit volume is low relative to
   trading traffic, so this global serialization is an acceptable cost.

## Recorded fields

Each entry captures: timestamp, actor (user id + type), tenant
(`organization_id`), IP (hashed), request id, **correlation id**, **session id**,
action, resource type/id, and **before/after state** — plus the chain fields
(`sequence`, `prev_hash`, `entry_hash`).

## Covered events

Login, logout, password reset, API keys, broker added/updated/deleted, strategy
lifecycle, order lifecycle, risk triggers, subscription changes, payments, and
admin actions are recorded by their owning modules through `AuditService.record`.

## Searchable UI

`/app/audit` (permission `AUDIT_VIEW`) filters by action prefix, resource type,
correlation id, actor, and date range, and expands each entry to show the
before/after diff and its `entry_hash`. The API is `GET /api/v1/audit-events`.

## Verifying integrity

Platform admins can recompute the chain:

```
GET /api/v1/admin/audit-events/integrity?limit=10000
→ { "checked": 10000, "intact": true, "first_bad_sequence": null }
```

`intact: false` with a `first_bad_sequence` means the chain broke at (or before)
that sequence — evidence of tampering or data loss to investigate immediately.

## Rollback

- **Schema/trigger:** `alembic downgrade 0005` drops the trigger, indexes, and
  chain columns. The base audit trail (actor/action/before/after) keeps working.
- **Code:** isolated to the `phase-3-audit` branch; new `record()` parameters are
  optional and additive, so `git revert` is safe. The advisory-lock write path
  degrades to a plain append if the chain columns are absent.
