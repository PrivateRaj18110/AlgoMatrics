# Enterprise security (Phase 17)

Two additive controls: OWASP security response headers on every response, and a
per-organization IP allowlist.

## Security response headers

`shared/infrastructure/security_headers.py` is a pure policy; `SecurityHeadersMiddleware`
applies it as the **outermost** layer, so every response — including CORS
preflights and error responses — is stamped. Headers set:

| Header | Value |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `Cross-Origin-Resource-Policy` | `same-origin` |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=(), payment=()` |
| `Content-Security-Policy` | locked-down for the API; relaxed only for the dev docs page |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` — **staging/production only** |

HSTS is withheld in `local`/`test` so plain-HTTP development is not broken.
Controlled by `SECURITY_HEADERS_ENABLED` (default `true`). Existing handlers
that set a header deliberately win — the middleware only fills gaps.

## Organization IP allowlist

`organizations/domain/ip_allowlist.py` (pure) validates and matches IPv4/IPv6
addresses and CIDR ranges. The allowlist is stored under the `ip_allowlist` key
of the organization's `settings` JSON — **no new table**.

- **Empty allowlist ⇒ unrestricted** (the default; no behaviour change for
  existing organizations).
- Once entries exist, a request's client IP must fall inside one of them, or the
  tenant dependency raises `403`. An unparseable IP **fails closed** when an
  allowlist is configured.

Enforcement runs in `get_tenant_context` after the membership check, so it
guards every tenant-scoped route. Management is owner/admin-only and audited:

- `GET /api/v1/organizations/current/ip-allowlist`
- `PUT /api/v1/organizations/current/ip-allowlist` — validates + de-dupes; up to
  100 entries.

> **Deployment note:** enforcement uses the socket peer IP (`request.client.host`).
> Behind a load balancer / reverse proxy, terminate a trusted proxy layer that
> sets the real client IP (e.g. via `X-Forwarded-For` handling at the edge)
> before this check, or the allowlist will see the proxy's address.

## Frontend

Settings → Organization gains an **IP allowlist** card (one entry per line,
owner/admin editable).

## Rollback

Fully additive and reversible with no migration: the allowlist lives in existing
`settings` JSON, and headers are gated by `SECURITY_HEADERS_ENABLED`. Revert the
`phase-17-enterprise-security` branch to remove the code.

## Security notes

- The allowlist is fail-closed once configured; empty = allow-all to preserve
  compatibility.
- Header policy is centralized and unit-tested; HSTS is environment-gated.
- Allowlist changes are recorded in the immutable audit log.
