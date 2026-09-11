# Backup and restore — monitoring.v1 tables

## 1. What is irreplaceable

Only one table: **`monitoring_evidence`**.

Everything else is either derived from it or is forensic material about traffic that never became monitoring data:

| Table | Recoverable? |
|---|---|
| `monitoring_evidence` | **No.** This is what LLS actually said. Losing it loses history permanently. |
| `monitoring_projections` | Yes — `projections.rebuild()` regenerates it exactly |
| `monitoring_sequence_state` | Partially — counters would restart; gap history is lost |
| `monitoring_conflicts` | No, but re-derivable by replaying evidence through the receiver |
| `monitoring_quarantine` | No — but it describes data that was never valid |
| `monitoring_raw_requests` | No — forensic only |
| `monitoring_audit` | No — security record, should be retained per policy |

A backup that captures `monitoring_evidence` captures the system's memory. A backup that captures only projections captures a view that can be rebuilt anyway.

## 2. Before migrating

The upgrade is additive — seven new tables, no `ALTER` on anything existing — so it is safe to apply to a running deployment and the previous image ignores the new tables.

**The downgrade is not safe.** `downgrade()` drops `monitoring_evidence`, which destroys received evidence. Take a backup first:

```bash
pg_dump --format=custom --table='monitoring_*' "$OPS_DATABASE_URL" > monitoring-pre-migration.dump
```

On a first deployment there is nothing to back up, since the tables do not yet exist.

## 3. Restore

```bash
pg_restore --dbname="$OPS_DATABASE_URL" --clean --if-exists monitoring-pre-migration.dump
```

If only projections were lost or are suspected wrong, do not restore — rebuild:

```python
from app.database.session import get_sessionmaker
from app.monitoring.projections import rebuild

session = get_sessionmaker()()
rebuild(session)
session.commit()
```

`rebuild` deletes every projection row and replays evidence in publisher order. `test_rebuild_does_not_touch_evidence` asserts it leaves evidence alone.

## 4. Not done

| | |
|---|---|
| **NOT DONE** | no backup or restore was actually performed — there is no production deployment to back up |
| **NOT TESTED** | the `pg_dump` / `pg_restore` commands above are the standard forms and have not been executed against this schema |
| **NOT MEASURED** | `rebuild` cost at production evidence volume; it loads and replays every row in one session |
| **NOT IMPLEMENTED** | no scheduled backup job, no retention policy for evidence |
