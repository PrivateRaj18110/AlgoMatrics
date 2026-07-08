# Worker separation (Phase 7)

The single background worker is now a set of independently deployable **roles**
hosted by one thin process. A process runs the roles named in `WORKER_ROLES`
(default `["all"]`), so the same image scales any role to its own container.

## Roles

| Role | Kind | Responsibility |
|---|---|---|
| `relay` | outbox poller | Publish transactional-outbox events to the event bus |
| `email` | outbox poller | Deliver the transactional e-mail outbox |
| `notification` | event consumer | Fan significant events out to organization notifications |
| `analytics` | event consumer | Aggregate per-day event counters (Redis) |
| `audit` | event consumer | Consume security/admin events (SIEM seam) |
| `report` | event consumer | Trading/billing reporting seam |
| `billing` | event consumer | Billing-domain processing seam |
| `settlement` | event consumer | Payment/settlement processing seam |
| `trading` | event consumer | Trading-domain processing seam |

Event-consumer roles each use their **own consumer group** on the shared
`events` stream (built on the Phase 6 `StreamConsumer`), so they process in
parallel, retry independently, dead-letter poison messages, and dedupe via the
inbox. Prefix routing sends each role only the event types it cares about.

> The heavier domain mutations already run synchronously in the request/engine
> paths. `analytics` and `notification` do real async work today; `audit`,
> `report`, `billing`, `settlement`, and `trading` are observable per-domain
> consumer seams that domain teams extend without touching the request path.

## Orchestration

The runner supervises every selected role in-process: a role that crashes is
restarted with backoff so it cannot take down the others, and all roles stop
gracefully on `SIGTERM`.

**Single process (default, small deployments):** the base `worker` service runs
`["all"]`.

**Separated services (scale independently):**

```bash
docker compose -f docker-compose.yml -f docker-compose.workers.yml up -d
# scale a hot consumer:
docker compose -f docker-compose.yml -f docker-compose.workers.yml \
  up -d --scale worker-analytics=3
```

`docker-compose.workers.yml` narrows the base `worker` to `["relay","email"]`
and runs each domain consumer as its own service. Multiple replicas of a role
share its consumer group, so the stream is load-balanced across them safely.

## Rollback

Set `WORKER_ROLES=["all"]` (the default) to return to one process running every
role, or stop the `docker-compose.workers.yml` override. The split is isolated
to the `phase-7-worker-separation` branch with behaviour-preserving relay/email
extraction and no schema/API change, so `git revert` is safe.
