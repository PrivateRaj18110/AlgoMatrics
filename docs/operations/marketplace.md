# Strategy marketplace (Phase 10)

A store where an organization publishes one of its strategies for others to
license, review, and run. The whole surface is gated by the `marketplace`
feature flag (Phase 4), so it can be rolled out per tenant.

## Domain

- **Listing** — a published strategy with a pricing model (`free` / `one_time` /
  `subscription`), price, currency, and a `revenue_share_percent` (the
  publisher's cut). Lifecycle: `draft → published → unlisted`.
- **Review** — a 1–5 rating with a comment; one per organization, and only from
  organizations that hold a license.
- **License** — a grant to a licensee organization (`purchase` / `subscription`),
  with `active/expired/revoked` status and optional expiry.
- **Revenue split** — `revenue_split(gross, share)` divides gross into publisher
  earnings and platform fee (rounded to cents; the parts always sum back).

## API (`/api/v1/marketplace`, feature-gated)

| Method & path | Purpose |
|---|---|
| `POST /listings` | Publish an owned strategy (STRATEGIES_MANAGE) |
| `GET /listings` | Browse published listings with rating/license stats |
| `GET /listings/{id}` / `.../reviews` | Listing detail and reviews |
| `POST /listings/{id}/license` | Acquire a license |
| `POST /listings/{id}/reviews` | Review (license required) |
| `POST /listings/{id}/unlist` | Unlist (publisher) |
| `GET /licenses` | The caller's licenses |
| `GET /revenue` | Publisher revenue report by currency |

Publishing verifies the caller owns the strategy via the strategies read facade
(`StrategyDirectory.owns`).

## Frontend

`/app/marketplace` (nav entry shown only when the `marketplace` flag is enabled)
browses listings, shows rating/price/licensed counts, and acquires licenses.

## Payments & licensing

Free listings grant a license immediately. Paid listings record the license here;
payment capture is handled by the billing system (Phase 9) in the presentation
layer before the grant, and revenue is split by the listing's share. This keeps
the marketplace domain independent of the payment provider.

## Rollback

- **Runtime:** turn the `marketplace` feature flag off — the API denies and the
  nav entry disappears.
- **Schema:** `alembic downgrade 0009` drops the three marketplace tables.
- The module is self-contained and additive; `git revert` of the
  `phase-10-marketplace` branch removes it with no impact on other modules.
