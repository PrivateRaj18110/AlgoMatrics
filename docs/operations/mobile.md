# Mobile backend (Phase 16)

A `modules/mobile` bounded context adds the pieces a native app needs on top of
the existing JWT + rotating-refresh-token auth (already mobile-ready): a **device
registry** with push tokens, a **push provider** abstraction, and a **bootstrap
aggregate** that collapses a cold-start into one round-trip.

## Device registry

`mobile_devices` (migration `0014`) stores one row per device install: owning
user/org, `platform` (ios/android/web), the push token (globally unique),
optional app version and device name, and first/last-seen timestamps.

- `POST /api/v1/mobile/devices` — register (idempotent by push token: an
  existing token is re-homed to the current user/org rather than duplicated).
- `GET /api/v1/mobile/devices` — the caller's devices.
- `DELETE /api/v1/mobile/devices/{id}` — unregister (tenant + owner scoped).

Push tokens are validated (`normalize_push_token`: non-empty, length-bounded, no
whitespace) before storage; the provider remains the authority on real validity.

## Push delivery

`PushProvider` (port) + `NullPushProvider` (default) keep the platform hermetic
and functional without APNs/FCM credentials — the null provider logs and reports
success. `PUSH_PROVIDER=fcm` is recognised for forward compatibility and falls
back to the null provider until credentials + the FCM adapter are provisioned.

`DeviceService.push_to_user` fans a `PushMessage` (title/body clamped to
conservative display limits) to every registered device and **prunes any tokens
the provider reports invalid**, so stale installs stop receiving. The provider is
resolved from `app.state.push_provider` (`PushProviderDep`).

## Bootstrap aggregate

`GET /api/v1/mobile/bootstrap` returns, in one request:

- `user` — id, email, organization, role.
- `unread_notifications` — the notification badge count.
- `device_count` — registered devices.
- `features` — every feature flag evaluated for the caller.

This removes three-to-four separate calls from the mobile app's launch path.

## Frontend

Settings → Security gains a **Registered devices** card (list + unregister),
mirroring the active-sessions card.

## Configuration

| Setting | Default | Purpose |
|---|---|---|
| `PUSH_PROVIDER` | `null` | `null` logs (hermetic); `fcm` reserved for Firebase |
| `FCM_CREDENTIALS_JSON` | — | FCM service-account JSON (when `fcm`) |

## Rollback

Additive: one table (`alembic downgrade 0013`), the new module, and the `/mobile`
routes. Nothing in existing auth or notifications changes. Revert the
`phase-16-mobile-backend` branch to remove it.

## Security notes

- Device endpoints are tenant-scoped and owner-checked; a user can only see and
  revoke their own devices.
- Push tokens are validated on write; invalid tokens are pruned on send.
- The default provider never calls out — no credentials, no external egress.
