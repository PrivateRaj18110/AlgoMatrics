import type { ReactNode } from 'react'
import { TooltipProvider } from '@/components/ui/tooltip'
import { QueryProvider } from './QueryProvider'
import { SidebarProvider } from './SidebarProvider'
import { ThemeProvider } from './ThemeProvider'
import { SettingsProvider } from './SettingsProvider'

/** Single composition root for every app-wide provider. */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <SettingsProvider>
        <QueryProvider>
          <SidebarProvider>
            <TooltipProvider delayDuration={150}>{children}</TooltipProvider>
          </SidebarProvider>
        </QueryProvider>
      </SettingsProvider>
    </ThemeProvider>
  )
}
