import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { SidebarContext, type SidebarContextValue } from './sidebar'

const STORAGE_KEY = 'rqos.sidebar.collapsed'

/** Holds sidebar collapse (desktop) + drawer (mobile) state, persisted locally. */
export function SidebarProvider({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsedState] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem(STORAGE_KEY) === 'true'
  })
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, String(collapsed))
  }, [collapsed])

  const setCollapsed = useCallback((value: boolean) => setCollapsedState(value), [])
  const toggleCollapsed = useCallback(() => setCollapsedState((v) => !v), [])

  const value = useMemo<SidebarContextValue>(
    () => ({ collapsed, toggleCollapsed, setCollapsed, mobileOpen, setMobileOpen }),
    [collapsed, toggleCollapsed, setCollapsed, mobileOpen],
  )

  return <SidebarContext.Provider value={value}>{children}</SidebarContext.Provider>
}
