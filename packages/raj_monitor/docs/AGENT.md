# Raj Local Agent — internals & operations

This document explains how the agent works, its threads, its data flow, and how
it behaves under failure. For installation see [`../INSTALL_WINDOWS.md`](../INSTALL_WINDOWS.md)
and [`../INSTALL_LINUX.md`](../INSTALL_LINUX.md).

## Process model

The agent is a single process with a handful of daemon threads:

```
main thread ........ lifecycle / signal handling (SIGINT, SIGTERM)
http server ........ ThreadingHTTPServer on 127.0.0.1:8765 (SDK -> Agent)
register ........... one-shot backend registration (retried each cycle if down)
metrics loop ....... every metrics_sec: snapshot host -> queue
heartbeat loop ..... every heartbeat_sec: heartbeat -> queue
uploader loop ...... every upload_sec: pop a batch -> backend, delete on success
```

All telemetry — whether from the SDK or self-generated — funnels into **one
persistent queue**, and the uploader is the only thing that talks to the backend.

## Data flow

```
Strategy ──HTTP(localhost)──▶ /ingest ──▶ PersistentQueue (SQLite, WAL)
                                                   │
metrics/heartbeat loops ───────────────────────────┤
                                                   ▼
                                         uploader: peek_batch(N)
                                                   │  gzip + token
                                                   ▼
                                    POST /api/agent/batch  ──▶ backend
                                                   │
                                         success → delete rows
                                         failure → mark_attempt, keep rows
```

The envelope (`types.Envelope`) is the unit of work end to end:
`{id, kind, ts, strategy, machine, account?, protocol, data}`.

## The persistence guarantee

- The queue lives in a single SQLite file (`queue.db_path`) in WAL mode.
- `put()` commits before returning, so an item is durable the instant it is
  accepted — a crash one millisecond later still has it on disk.
- The uploader **peeks** a batch, uploads, and only then **deletes** those rows.
  If the process dies mid-upload, the rows remain and are re-sent next start.
- Overflow policy is **drop-oldest**: once the queue passes `queue.max_size`, the
  oldest rows are pruned so the freshest telemetry is always retained.

## Failure behaviour

| Failure | What happens |
| --- | --- |
| Backend down | Uploads fail, rows stay queued, circuit breaker trips after `breaker_threshold`. The agent keeps collecting. On recovery (after `breaker_cooldown_sec`) it drains the backlog. |
| Internet loss | Same as backend down — metrics still collected locally; `internetOk=false` flips the machine to *degraded*. |
| Agent restart / reboot | Queue reloaded from SQLite; nothing lost. Heartbeats resume; backend re-registration happens on the next cycle. |
| SDK can't reach agent | The SDK re-queues in memory and retries (bounded, drop-oldest) — the strategy is never blocked or raised into. |
| Queue overflow | Oldest items dropped; `dropped_total` exposed at `/stats`. |
| Bad/corrupt queue row | Skipped and deleted so it can't wedge the pipeline. |

## Local API (SDK ↔ Agent)

| Method & path | Purpose |
| --- | --- |
| `POST /ingest` | Accept one envelope (requires `X-Raj-Local-Token` if configured). |
| `GET /health` | `{status, agentId, machine}` |
| `GET /stats` | `{queued, uploaded, dropped, strategies, breaker, backend}` |

Bound to `127.0.0.1` only. Never expose this port off-host.

## Tuning for <1% CPU / <100 MB RAM

- Increase `intervals.metrics_sec` (process enumeration is the priciest call).
- Uninstall `psutil` to skip per-process listing (coarser metrics, lower cost).
- Raise `queue.batch_size` to amortise upload overhead on busy hosts.
- Keep `upload_sec` at 1–3s for snappy dashboards, higher to reduce request rate.

## Testing matrix

The scenarios required by the milestone and how to exercise them:

| Scenario | How to simulate | Expected |
| --- | --- | --- |
| Internet loss | Point `backend.url` at an unreachable host | Queue grows; `breaker` → open; no SDK errors |
| Backend restart | Stop/start uvicorn while agent runs | Backlog drains after restart; no loss |
| Queue overflow | Set `queue.max_size` low, flood events | `dropped_total` increases; newest kept |
| Machine restart | Kill agent, restart | `queued` count preserved across restart |
| High latency | Add latency/slow backend | Retries with backoff; uploads eventually succeed |
| Multiple strategies | Run several strategies against one agent | `/stats.strategies` reflects the count |
| Three machines | Run an agent per host (distinct `machine.name`) | Three live machines on the dashboard |

A scripted smoke test for the offline + overflow paths lives in
[`../tests/test_smoke.py`](../tests/test_smoke.py).
