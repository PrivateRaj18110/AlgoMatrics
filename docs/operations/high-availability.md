# High availability (Phase 18)

Two building blocks for running the API behind a load balancer / orchestrator
without cascading failures: hardened health probes and a reusable circuit
breaker.

## Health probes

| Endpoint | Purpose | Status semantics |
|---|---|---|
| `GET /api/v1/health/live` | Liveness — process is up | Always `200 ok` |
| `GET /api/v1/health/ready` | Readiness — safe to route traffic | `200` when ready, **`503`** when a critical dependency is down |
| `GET /api/v1/health/dependencies` | Operator introspection | Always `200` with per-component detail |

Each dependency probe (Postgres, Redis) is bounded by
`READINESS_TIMEOUT_SECONDS` (`asyncio.timeout`), so a hung dependency cannot
block the probe itself. The roll-up rule is pure and unit-tested
(`shared/application/readiness.py`): the service is `ok` only when every
**critical** component is healthy; a failing non-critical component is reported
but does not pull the replica from rotation.

**Configure your orchestrator** to poll `/health/ready` and remove the instance
from rotation on `503`, and `/health/live` for restart decisions.

## Circuit breaker

`shared/application/circuit_breaker.py` is a reusable, clock-injectable state
machine:

```
closed --(failure_threshold consecutive failures)--> open
open   --(reset_timeout elapsed)--------------------> half_open
half_open --(trial success)-> closed   --(trial failure)-> open
```

`await breaker.call(coro)` runs the coroutine, records success/failure, and
rejects fast with `CircuitOpenError` while open — so a failing dependency stops
consuming workers on doomed calls. Defaults:
`CIRCUIT_BREAKER_FAILURE_THRESHOLD` (5) and `CIRCUIT_BREAKER_RESET_SECONDS` (30).

It is wired around the **notification webhook channel** today (repeated webhook
failures open the breaker; the dispatcher swallows the fast rejection so the
in-app notification is unaffected). The primitive is generic and can wrap any
flaky outbound call (broker adapters, providers).

## Frontend

None — these are infrastructure endpoints for load balancers and orchestrators,
not a user-facing surface.

## Rollback

Fully additive, no migration: new shared modules, a probe upgrade, and an
optional breaker on one channel. Revert the `phase-18-high-availability` branch
to remove it. Setting the thresholds high effectively disables tripping.

## Notes

- Readiness returning `503` is intentional and required for LB integration — it
  is not an error to alert on unless it persists.
- The breaker uses a monotonic clock and holds no I/O; it is safe to share one
  instance across requests.
