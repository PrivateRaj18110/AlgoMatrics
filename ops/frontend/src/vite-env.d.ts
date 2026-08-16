/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the backend API. When unset the app uses the mock data layer. */
  readonly VITE_API_BASE_URL?: string
  /** Force the mock data layer even when an API base URL is configured. */
  readonly VITE_USE_MOCK?: string
  /** Public application version, surfaced in the UI / about screens. */
  readonly VITE_APP_VERSION?: string
  /**
   * Viewer credential for REST dashboard APIs. Prefer a per-user platform JWT
   * when available. If unset, the client falls back to VITE_OPS_WS_TOKEN so one
   * local/prod dashboard credential can unlock both REST reads and websocket.
   */
  readonly VITE_OPS_API_TOKEN?: string
  /**
   * Viewer credential for the telemetry websocket (`/api/ws`). Sent in the
   * `Sec-WebSocket-Protocol` header, never the query string. Without it the
   * backend refuses the handshake and the live feed stays empty.
   *
   * Note: a build-time value is embedded in the bundle, so it authenticates
   * "a dashboard", not "a person". Where the platform login is available,
   * configure `OPS_JWT_PUBLIC_KEY` on the backend and supply a per-user
   * platform access token here instead.
   */
  readonly VITE_OPS_WS_TOKEN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
