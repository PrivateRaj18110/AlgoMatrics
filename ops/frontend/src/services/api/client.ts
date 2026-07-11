import { MOCK_LATENCY_MS } from '@/utils/constants'

/**
 * Thin API client + mock bridge.
 * ----------------------------------------------------------------------------
 * Every domain service goes through here. While `USE_MOCK` is true (default,
 * and whenever no API base URL is configured) services resolve bundled
 * fixtures. Flip `VITE_USE_MOCK=false` and point `VITE_API_BASE_URL` at the
 * FastAPI backend to switch the whole app onto real data — no component changes
 * required.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''

export const USE_MOCK =
  import.meta.env.VITE_USE_MOCK === 'true' || API_BASE_URL === ''

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * Resolve a deep-cloned copy of a fixture after a simulated network delay, so
 * loading / skeleton states behave like production and callers can safely
 * mutate the result.
 */
export async function mockResponse<T>(data: T, latency = MOCK_LATENCY_MS): Promise<T> {
  await delay(latency)
  return structuredClone(data)
}

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Real GET request used once a live backend is wired up. */
export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    throw new ApiError(`Request to ${path} failed`, res.status)
  }
  return (await res.json()) as T
}
