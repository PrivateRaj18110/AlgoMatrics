import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { AppSettings } from '@/types'
import { DEFAULT_SETTINGS } from '@/types'
import { settingsService } from '@/services'
import { SettingsContext, type SettingsContextValue } from './settings'

/**
 * Loads persisted settings once on mount and exposes a patch-and-persist
 * `update`. Settings drive the polling cadence and notification rules across
 * the app; theme remains owned by <ThemeProvider> and is mirrored here.
 */
export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let active = true
    settingsService.get().then((s) => {
      if (active) {
        setSettings(s)
        setLoaded(true)
      }
    })
    return () => {
      active = false
    }
  }, [])

  const update = useCallback((patch: Partial<AppSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch }
      void settingsService.save(next)
      return next
    })
  }, [])

  const value = useMemo<SettingsContextValue>(
    () => ({ settings, update, loaded }),
    [settings, update, loaded],
  )

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>
}
