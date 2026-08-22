import type { AppSettings } from '@/types'
import { DEFAULT_SETTINGS } from '@/types'
import { apiGet, mockResponse, USE_MOCK } from './api/client'

const STORAGE_KEY = 'rajquant.settings'

/** Merge persisted settings over the defaults (forward-compatible). */
function readLocal(): AppSettings {
  if (typeof localStorage === 'undefined') return DEFAULT_SETTINGS
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_SETTINGS
    return { ...DEFAULT_SETTINGS, ...(JSON.parse(raw) as Partial<AppSettings>) }
  } catch {
    return DEFAULT_SETTINGS
  }
}

function writeLocal(settings: AppSettings) {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
}

/**
 * Settings persist to localStorage in mock mode; the same surface targets the
 * backend `/settings` endpoint once the database is wired up.
 */
export const settingsService = {
  get(): Promise<AppSettings> {
    if (USE_MOCK) return mockResponse(readLocal(), 60)
    return apiGet<AppSettings>('/settings')
  },
  save(settings: AppSettings): Promise<AppSettings> {
    if (USE_MOCK) {
      writeLocal(settings)
      return mockResponse(settings, 60)
    }
    return apiGet<AppSettings>('/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    })
  },
}
