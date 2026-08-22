import { createContext, useContext } from 'react'

export interface SidebarContextValue {
  /** Desktop rail collapsed to icons only. */
  collapsed: boolean
  toggleCollapsed: () => void
  setCollapsed: (value: boolean) => void
  /** Mobile / tablet off-canvas drawer open state. */
  mobileOpen: boolean
  setMobileOpen: (value: boolean) => void
}

export const SidebarContext = createContext<SidebarContextValue | null>(null)

/** Access the sidebar collapse/drawer state. */
export function useSidebar(): SidebarContextValue {
  const ctx = useContext(SidebarContext)
  if (!ctx) {
    throw new Error('useSidebar must be used within <SidebarProvider>')
  }
  return ctx
}
