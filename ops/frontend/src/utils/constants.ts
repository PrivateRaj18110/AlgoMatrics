/** Static, app-wide constants. */

export const APP_NAME = 'Raj Quant OS'
export const APP_VERSION = import.meta.env.VITE_APP_VERSION ?? '1.0.0'

/** TanStack Query default refetch / stale windows (ms). */
export const QUERY_STALE_TIME = 15_000
export const QUERY_REFETCH_INTERVAL = 30_000

/** Simulated network latency for the mock data layer (ms). */
export const MOCK_LATENCY_MS = 280

/** Thresholds that drive status colouring for machine resources. */
export const RESOURCE_THRESHOLDS = {
  warning: 70,
  danger: 90,
} as const

/** Latency thresholds (ms) used across strategy + trade views. */
export const LATENCY_THRESHOLDS = {
  warning: 120,
  danger: 250,
} as const
