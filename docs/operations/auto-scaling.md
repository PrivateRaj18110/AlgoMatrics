# Auto scaling (Phase 19)

Horizontal scaling driven by queue backlog for the event workers, and CPU for
the stateless API tier. The scaling *math* is a pure, unit-tested policy; the
runtime signal is Redis consumer-group lag, surfaced as a Prometheus gauge and
an admin endpoint.

## Scaling policy (`shared/application/scaling.py`, pure)

`desired_replicas(backlog, config)` = `ceil(backlog / target_backlog_per_replica)`
clamped to `[min_replicas, max_replicas]`; empty backlog scales to the minimum.
`recommend(backlog, current, config)` adds a `scale_up | scale_down | hold`
verdict. Configured via `SCALING_TARGET_BACKLOG_PER_REPLICA`,
`SCALING_MIN_REPLICAS`, `SCALING_MAX_REPLICAS`.

## Signals

Workers consume the shared `events` stream, each under its own consumer group
**`worker:<role>`** (e.g. `worker:notification`, `worker:trading`).

- **Prometheus**: the infra sampler publishes `stream_depth{stream="events"}`
  (the stream length) every 15s — scrape it for dashboards/HPA-via-adapter.
- **Admin API**: `GET /api/v1/admin/scaling` (platform-admin) returns the stream
  depth plus, for each group in `SCALING_CONSUMER_GROUPS`, the current backlog
  (`XINFO GROUPS` lag, falling back to pending) and the recommended replica
  count.

## KEDA (workers)

`deploy/autoscaling/keda-scaledobjects.yaml` defines `ScaledObject`s that scale
each worker Deployment on its consumer group's pending backlog via KEDA's
`redis-streams` scaler. `pendingEntriesCount` mirrors
`SCALING_TARGET_BACKLOG_PER_REPLICA`; `pollingInterval` matches the sampler.

```
kubectl apply -f deploy/autoscaling/keda-scaledobjects.yaml
```

Each worker role runs as its own Deployment with `WORKER_ROLES='["<role>"]'` (the
same split as `deploy/compose/docker-compose.workers.yml`), so a hot role scales
independently.

## HPA (API tier)

`deploy/autoscaling/hpa-api.yaml` scales the stateless API on CPU (target 70%),
min 2 / max 12. Because `/health/ready` returns 503 while a dependency is down
(Phase 18), new replicas receive traffic only once healthy.

## Rollback

Fully additive, no migration: pure policy + reporter + one admin endpoint + a
gauge population + YAML manifests. Delete the `ScaledObject`s/HPA to stop
autoscaling; revert the `phase-19-auto-scaling` branch to remove the code.

## Notes

- Backlog lag needs Redis 7+ for the `lag` field; older servers fall back to the
  pending count.
- Set `SCALING_MAX_REPLICAS` in the app to match the KEDA `maxReplicaCount` so
  the reported recommendation and the actual ceiling agree.
