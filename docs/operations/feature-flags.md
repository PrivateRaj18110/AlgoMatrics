# Enterprise feature flags (Phase 4)

Runtime-configurable feature flags with **no deployment required**. Flags gate
capabilities such as the marketplace, AI assistant, paper/live trading, and each
broker integration, and support gradual rollout and an emergency kill switch.

## Evaluation model

For a given caller (environment + tenant + user), a flag is evaluated with this
precedence, most specific first:

1. **Kill switch** — emergency off; overrides everything.
2. **User override** — explicit on/off for one user.
3. **Tenant override** — explicit on/off for an organization.
4. **Environment override** — explicit on/off for `local`/`staging`/`production`.
5. **Percentage rollout** — deterministic per-subject bucketing (a user's result
   is stable across requests).
6. **Default** — the flag's `enabled` value.

Overrides are explicit decisions and therefore bypass the percentage rollout.
Evaluation logic is pure (`modules/feature_flags/domain/flags.py`) and unit
tested; the flag set is cached in Redis for a short TTL and invalidated on every
write, so checks are cheap without going stale.

## Seeded flags

`marketplace`, `ai`, `paper_trading` (on), `live_trading`, and per-broker gates
`broker.paper` (on), `broker.zerodha`, `broker.angelone`, `broker.delta`,
`broker.binance`, `broker.interactive_brokers`, `broker.mt5`. Unknown flag keys
evaluate to **off**.

## Using flags

**Backend — gate a route:**

```python
from fastapi import Depends
from algo_platform.modules.feature_flags.presentation.dependencies import require_feature

@router.post("/live-orders", dependencies=[Depends(require_feature("live_trading"))])
async def place_live_order(...): ...
```

**Frontend — gate UI:**

```tsx
import { Feature, useFeatureEnabled } from "@/lib/features";

<Feature flag="marketplace"><MarketplaceNav /></Feature>;
const aiEnabled = useFeatureEnabled("ai");
```

## Administration

Platform admins manage flags at **Admin → Feature Flags** (`/app/admin/feature-flags`)
or via the API:

| Method & path | Purpose |
|---|---|
| `GET /api/v1/feature-flags` | Evaluate all flags for the current caller |
| `GET /api/v1/admin/feature-flags` | List flag definitions |
| `PUT /api/v1/admin/feature-flags/{key}` | Create/update a flag (enabled, kill switch, rollout %) |
| `GET /api/v1/admin/feature-flags/{key}/overrides` | List scoped overrides |
| `PUT /api/v1/admin/feature-flags/{key}/overrides` | Set an environment/tenant/user override |
| `DELETE /api/v1/admin/feature-flags/{key}/overrides` | Clear an override |

Every admin mutation is recorded to the immutable audit log as an admin action.

## Rollback

- **Runtime:** flip the kill switch, or set `enabled=false` — no deploy.
- **Schema:** `alembic downgrade 0006` drops both tables.
- **Code:** isolated to the `phase-4-feature-flags` branch; nothing else depends
  on the flags yet, so `git revert` is safe. Unknown/absent flags evaluate to off.
