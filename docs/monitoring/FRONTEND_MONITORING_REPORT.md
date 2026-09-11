# Frontend monitoring report

## 1. Which UI is authoritative — a correction

The plan for this work named `ops/frontend` as the target, chosen on the basis that it has twenty operations pages while the platform frontend had two. **That was wrong, and the instruction to identify the authoritative UI before touching anything is what surfaced it.**

`ops/frontend` is retired. The evidence:

- [`ops/frontend/src/App.tsx`](../../ops/frontend/src/App.tsx) is a redirect shell: *"The Ops UI is no longer a public product"* → `window.location.replace('/app/dashboard')`. Its twenty pages are unreachable.
- [`deploy/nginx/nginx.conf`](../../deploy/nginx/nginx.conf): `location = /ops { return 302 /app/dashboard; }` — the redirect is enforced at the edge too.
- Commit `2050759` *"feat: unify app and operations UI"*: *"redirect /ops UI while keeping ops-api ingest"*.

So: **`ops/backend` is live** (which is why the receiver belongs there — nginx still proxies `/ops/api/`), and **`frontend/` is the authoritative UI** at `/app/*`.

The monitoring UI was therefore built in `frontend/`. `ops/frontend` was **not modified** — adding a page to a redirect shell would have produced code nobody can reach.

## 2. What was built

| File | Role |
|---|---|
| `frontend/src/lib/monitoring.ts` | types, `evaluateFreshness`, qualified-value helpers |
| `frontend/src/components/monitoring/QualifiedValue.tsx` | the one place a monitoring value becomes pixels |
| `frontend/src/components/monitoring/FreshnessBadge.tsx` | freshness, runtime and trust badges |
| `frontend/src/pages/operations/MonitoringPage.tsx` | the page, at `/app/lls-monitoring` |
| `frontend/src/lib/hooks.ts` | `useMonitoringState`, `useMonitoringSources`, `useMonitoringConflicts` |

Routed in `app/router.tsx`, linked in `app/AppLayout.tsx` as a **separate** sidebar entry from System Health — the two show independent protocols, and merging them in the nav would imply they agree.

## 3. The shared qualified-value component

One component renders all nine states, each visibly distinct:

| State group | Treatment | Rationale |
|---|---|---|
| `KNOWN` | plain content | the only state that gets to look like a fact |
| `UNKNOWN`, `INCOMPLETE` | amber | something is wrong with our knowledge, not necessarily with trading |
| `STALE`, `UNTRUSTED` | orange / rose | the number on screen may mislead |
| `UNSUPPORTED`, `N/A` | quiet grey | nothing is wrong; the field does not apply |
| `SIMULATED`, `SYNTHETIC_CLOCK` | violet | can never be mistaken for live trading |

`UNKNOWN` renders the **word** `UNKNOWN` — not `0`, not `—`, not an empty cell, not a green tick. `QualifiedValue.test.tsx` asserts the absence of `0` and `—` in that render.

A bare scalar reaching the component renders as `UNQUALIFIED` in red rather than being displayed normally. Silently accepting it would hide exactly the regression this component exists to catch.

## 4. Stale is obvious, and dated

`FreshnessBadge` renders the state as a word **plus** `LAST UPDATE: <time>`, for every state — not a recoloured number. When no horizon was supplied it adds "no validity horizon supplied" rather than showing green.

The verdict recomputes on a one-second timer. A page left open on a wall display crosses into STALE on its own, without a refetch. This is the difference between fixing the bug and moving it behind a poll interval.

## 5. Runtime and trust

`RuntimeBadge` marks anything that is not `LIVE` in violet with an explanatory tooltip. Historical and simulated data on a monitoring screen is legitimate; it is only dangerous when indistinguishable from live trading.

`TrustBadge` shows the publisher's level verbatim and renders `TRUST UNKNOWN` when none was stated. Successful HTTP delivery never upgrades it — a 200 means the message arrived, not that the trading state is correct.

## 6. What the page does not do

- It forms no opinion about whether LLS is healthy. `core_status` carries Monitoring's verdict and the page displays it, including when that verdict is `UNKNOWN`.
- It computes no coverage percentage. `coverage.ratio` renders through `QualifiedValue`, so an unsupplied ratio shows `UNKNOWN` — never `0%`, never `100%`.
- It offers no control. There is no button, form or mutation on the page.
- It distinguishes "no monitoring database configured" from "no updates received" — different facts an operator would act on differently.

## 7. The legacy pages were left alone

`frontend/src/lib/unknown.ts` renders missing agent telemetry as `—`. Monitoring values do not use it.

System Health, Machines, Events and the rest display the `raj_monitor` agent protocol, which carries no knowledge-state vocabulary. Retrofitting one would mean inventing states the agent never sent. They remain as they were, and **they can still show a stale agent value as current** — a real limitation, blocked on that protocol rather than on this work.

## 8. Status

| | |
|---|---|
| **IMPLEMENTED** | qualified-value rendering for all nine states, live freshness, runtime/trust badges, monitoring page, route, nav |
| **TESTED** | 32 tests (12 logic, 20 component), all passing |
| **VERIFIED** | `tsc -b` clean, `eslint` clean, full frontend suite passing |
| **NOT DONE** | the page has no test of its own — the components and logic beneath it are tested, the composition is not |
| **NOT DONE** | no visual/responsive check in a real browser; layout is unverified below tablet width |
| **NOT DONE** | UNKNOWN/STALE on the legacy agent pages — see §7 |
