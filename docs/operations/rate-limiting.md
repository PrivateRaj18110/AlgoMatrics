# Enterprise rate limiting (Phase 5)

Redis-backed **sliding-window** rate limiting across six scopes with burst
control and runtime admin overrides. Replaces the previous fixed-window limiter.

## Algorithm

A sorted-set log per key: on each request expired entries are trimmed, the hit
is recorded scored by timestamp, and the current count is compared to the limit
— one Redis pipeline round-trip per check
(`RedisGateway.sliding_window_hit`). Each rule may add a short **burst** window
(e.g. 20/sec on top of 600/min); both the sustained and burst windows must pass.
The decision logic (`shared/infrastructure/rate_limiting/limiter.py`) is pure and
unit tested via an in-memory store.

## Scopes

`tenant`, `user`, `api_key`, `ip`, `broker`, `route`. A request is denied if
**any** applicable scope is exceeded.

| Where | Scope(s) | How |
|---|---|---|
| `RateLimitMiddleware` | `ip` | Global per-IP limit on every non-exempt request (health/metrics exempt). |
| `rate_limit(name, …)` dependency | `ip` + route `name` | Per-route IP limit (auth endpoints). |
| `scoped_rate_limit(name, …, scopes=…)` dependency | any of the six | Applied to a specific route; API keys are hashed, broker is read from a path param. |

Example — cap live-order submission per tenant, user, and API key:

```python
from fastapi import Depends
from algo_platform.api.dependencies.rate_limit import scoped_rate_limit
from algo_platform.shared.infrastructure.rate_limiting.scopes import Scope

@router.post(
    "/live-orders",
    dependencies=[Depends(scoped_rate_limit(
        "live_orders", times=60, seconds=60, burst=5,
        scopes=(Scope.TENANT, Scope.USER, Scope.API_KEY),
    ))],
)
async def place_live_order(...): ...
```

## Responses

A throttled request gets `429` with an RFC 9457 problem body, `Retry-After`, and
`X-RateLimit-Limit` / `X-RateLimit-Remaining` headers. Allowed requests carry the
same rate-limit headers. All limiters **fail open** if Redis is unavailable.

## Admin overrides (no deployment)

Platform admins can retune a named limit or exempt a subject at runtime; each
change is written to the audit log.

| Method & path | Purpose |
|---|---|
| `PUT /api/v1/admin/rate-limits/config/{name}` | Override a named limit (limit, window, burst) |
| `DELETE /api/v1/admin/rate-limits/config/{name}` | Revert to the coded default |
| `PUT /api/v1/admin/rate-limits/bypass` | Exempt a `{scope, subject}` (e.g. a monitoring IP) |
| `DELETE /api/v1/admin/rate-limits/bypass` | Remove a bypass |

The global IP limiter reads `config/ip` and IP bypasses; scoped dependencies read
`config/{name}` and per-scope bypasses.

## Configuration

```
RATE_LIMIT_ENABLED=true
IP_RATE_LIMIT_PER_MINUTE=600
IP_RATE_LIMIT_BURST_PER_SECOND=30
```

## Rollback

- **Runtime:** `RATE_LIMIT_ENABLED=false` disables the global middleware and the
  limiter build; per-route dependencies fail open without a limiter.
- **Code:** isolated to the `phase-5-rate-limiting` branch; no schema or
  API-contract change, so `git revert` is safe. `rate_limit()` kept its
  signature, so existing callers are unaffected.
