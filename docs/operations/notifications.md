# Notifications (Phase 15)

The platform ships in-app notifications with live WebSocket fan-out. Phase 15
adds **multi-channel delivery** — email and outbound webhook — driven by
per-recipient **delivery preferences**. In-app remains the always-on baseline;
email/webhook are strictly opt-in.

## Routing rules (`notifications/domain/delivery.py`, pure)

`resolve_channels(preference, type_, severity, local_time)` decides which
channels a notification reaches for one recipient:

- **In-app** is always included (the record is written regardless) unless the
  notification `type` is muted.
- **Email / webhook** are included only when the recipient enabled them, the
  severity is at or above `min_severity`, and the moment is outside the
  recipient's quiet hours.
- **Quiet hours** are a daily do-not-disturb window in the recipient's local
  time, and may wrap past midnight (e.g. 22:00 → 07:00). `critical` severity
  bypasses quiet hours unless `critical_overrides_quiet` is disabled.

All of this is pure and unit-tested (`tests/unit/test_notification_delivery.py`).

## Channels (`notifications/infrastructure/channels.py`)

- `EmailNotificationChannel` — sends via the app's `EmailSender`.
- `WebhookNotificationChannel` — `POST`s JSON to an operator-configured URL.
  The URL passes an **SSRF guard** (`validate_webhook_url`): HTTPS only, and
  literal loopback / private / link-local / reserved / multicast hosts are
  rejected.
- `NotificationDispatcher` fans out to the enabled channels. **Channel failures
  are logged, never raised** — a webhook outage cannot break the in-app
  notification (already persisted) or the business transaction that triggered
  it. `build_dispatcher` wires it from the shared email sender + a shared
  `httpx.AsyncClient` (created in the app lifespan, closed on shutdown).

`NotificationService.notify(..., delivery=ExternalDelivery(...))` opts a single
call into external fan-out. Without `delivery` the method behaves exactly as
before (in-app record + Redis publish only) — the change is additive.

## Preferences

`notification_preferences` (migration `0013`, one row per user/org) stores the
enabled channels, muted types, `min_severity`, quiet-hours window,
`critical_overrides_quiet`, and `webhook_url`.

- `GET /api/v1/notifications/preferences` — current policy (defaults to in-app
  only when unset).
- `PUT /api/v1/notifications/preferences` — update it. The webhook URL is
  re-validated by the SSRF guard on write; unknown channels/severities are
  dropped to safe defaults.

## Frontend

Settings → Notifications gains a **Delivery channels** card: email/webhook
toggles, webhook URL (shown when webhook is on), minimum severity, quiet-hours
window, and the critical-override switch.

## Rollback

Additive: one table (`alembic downgrade 0012`), the new channels/preferences
code, and two endpoints. Existing in-app + WebSocket delivery is untouched.
Revert the `phase-15-notifications` branch to remove it.

## Security notes

- Webhook targets are operator-supplied → SSRF guard on both write and send.
- Channel delivery is best-effort and isolated; failures never propagate.
- No secrets are logged; webhook failures log only the URL host context via the
  structured redaction processor.
