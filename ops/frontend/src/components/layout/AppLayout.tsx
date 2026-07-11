import { Suspense, useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { Sheet, SheetContent } from '@/components/ui/sheet'
import { Sidebar } from '@/components/navigation/Sidebar'
import { TopBar } from './TopBar'
import { PageSkeleton } from './PageSkeleton'
import { PageTransition } from './PageTransition'
import { useSidebar } from '@/providers/sidebar'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { useRealtime } from '@/hooks/useRealtime'
import { cn } from '@/utils/cn'

/**
 * Application shell: fixed collapsible sidebar (desktop), off-canvas drawer
 * (tablet / mobile) and a sticky top bar wrapping the routed content.
 */
export function AppLayout() {
  const { collapsed, toggleCollapsed, mobileOpen, setMobileOpen } = useSidebar()
  const isDesktop = useMediaQuery('(min-width: 1024px)')

  // Subscribe to the realtime feed once for the whole app shell.
  useRealtime()

  // Ensure the mobile drawer never lingers open when returning to desktop.
  useEffect(() => {
    if (isDesktop && mobileOpen) setMobileOpen(false)
  }, [isDesktop, mobileOpen, setMobileOpen])

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background text-foreground">
      {/* Desktop rail */}
      <aside
        className={cn(
          'hidden shrink-0 border-r border-border transition-[width] duration-200 ease-out lg:block',
          collapsed ? 'w-16' : 'w-60',
        )}
      >
        <Sidebar collapsed={collapsed} onToggleCollapse={toggleCollapsed} />
      </aside>

      {/* Mobile / tablet drawer */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="w-60 p-0" hideClose>
          <Sidebar collapsed={false} onNavigate={() => setMobileOpen(false)} />
        </SheetContent>
      </Sheet>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="flex-1 overflow-y-auto scrollbar-thin">
          <div className="mx-auto w-full max-w-[1600px] space-y-5 p-3 sm:p-4 lg:p-6">
            <PageTransition>
              <Suspense fallback={<PageSkeleton />}>
                <Outlet />
              </Suspense>
            </PageTransition>
          </div>
        </main>
      </div>
    </div>
  )
}
