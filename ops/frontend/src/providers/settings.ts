import { createContext, useContext } from 'react'
import type { AppSettings } from '@/types'
import { DEFAULT_SETTINGS } from '@/types'

export interface SettingsContextValue {
  settings: AppSettings
  /** Patch + persist one or more settings. */
  update: (patch: Partial<AppSettings>) => void
  /** Whether the initial load has resolved. */
  loaded: boolean
}

export const SettingsContext = createContext<SettingsContextValue>({
  settings: DEFAULT_SETTINGS,
  update: () => {},
  loaded: false,
})

/** Access the live application settings. */
export function useSettings(): SettingsContextValue {
  return useContext(SettingsContext)
}

/** Auto-refresh cadence (ms) derived from settings — used by every data hook. */
export function useRefetchInterval(): number {
  return useContext(SettingsContext).settings.refreshIntervalSec * 1000
}
