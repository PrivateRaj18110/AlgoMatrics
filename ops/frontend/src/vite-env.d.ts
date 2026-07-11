/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the backend API. When unset the app uses the mock data layer. */
  readonly VITE_API_BASE_URL?: string
  /** Force the mock data layer even when an API base URL is configured. */
  readonly VITE_USE_MOCK?: string
  /** Public application version, surfaced in the UI / about screens. */
  readonly VITE_APP_VERSION?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
