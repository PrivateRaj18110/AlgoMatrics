# Strategy versioning (Phase 14)

Semantic versions, diff, validation, an approval workflow, and deployment history
on top of the existing immutable `StrategyVersion` records.

## Domain (`strategies/domain/versioning.py`, pure)

- **`SemanticVersion`** — parse/compare/`bump_major|minor|patch`.
- **`diff_versions(old, new)`** — added/removed/changed parameters plus entry-point
  and checksum changes, with `suggested_bump` (breaking → major, additive → minor,
  else patch).
- **`validate_manifest(manifest)`** — returns issues (missing entry point,
  duplicate parameters, `min > max`); empty means valid.
- **Approval workflow** — `ApprovalStatus` (`draft` → `pending_review` →
  `approved`/`rejected`) and a `transition(status, action)` state machine
  (`submit`, `approve`, `reject`, `withdraw`; rejected can be resubmitted). Illegal
  transitions raise.

All of the above is pure and exhaustively unit-tested.

## Workflow

1. A new version starts as **draft**.
2. **Submit** it for review (`pending_review`).
3. A reviewer **approves** or **rejects** (with a note). Approval also sets the
   version's `approved_for_live` flag; rejection clears it. A rejected version can
   be resubmitted; a pending one can be withdrawn back to draft.
4. **Deploy** (or **rollback** to a prior version) is recorded in the deployment
   history with who and when.

## API (`/api/v1`, permission-gated, tenant-scoped)

| Method & path | Purpose |
|---|---|
| `POST /strategy-versions/{id}/submit` / `approve` / `reject` / `withdraw` | Advance the approval workflow (STRATEGIES_MANAGE) |
| `GET /strategy-versions/{id}/validate` | List manifest issues |
| `GET /strategy-versions/diff?from=&to=` | Structured diff of two versions |
| `POST /strategies/{id}/deploy` | Record a `deploy` or `rollback` of a version |
| `GET /strategies/{id}/deployments` | Deployment history |

Migration `0012` adds `strategy_version_approvals` and `strategy_deployments`.

## Frontend

The API is complete; surfacing the approval status, diff view, and deployment
timeline on the strategy detail page is a scoped follow-up. Reviewers can drive
the workflow via the API today.

## Rollback

Additive: two tables (`alembic downgrade 0011`) and new endpoints; the existing
`StrategyVersion` records and runtime are untouched. Revert the
`phase-14-strategy-versioning` branch to remove it.
