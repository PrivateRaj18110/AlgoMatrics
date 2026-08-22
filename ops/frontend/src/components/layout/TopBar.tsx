import { Menu } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Clock } from '@/components/widgets/Clock'
import { ConnectionStatus } from '@/components/widgets/ConnectionStatus'
import { ThemeToggle } from '@/components/widgets/ThemeToggle'
import { NotificationsSheet } from '@/components/dialogs/NotificationsSheet'
import { useSidebar } from '@/providers/sidebar'
import { APP_NAME } from '@/utils/constants'

/** Global top bar: project identity, live clock, feed status and actions. */
export function TopBar() {
  const { setMobileOpen } = useSidebar()

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-background/80 px-3 backdrop-blur sm:px-4">
      {/* Mobile drawer trigger */}
      <Button
        variant="ghost"
        size="icon"
        className="size-9 lg:hidden"
        onClick={() => setMobileOpen(true)}
        aria-label="Open navigation"
      >
        <Menu className="size-5" />
      </Button>

      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold tracking-tight">{APP_NAME}</span>
        <span className="hidden rounded bg-primary/15 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-primary sm:inline">
          v1.0
        </span>
      </div>

      <div className="ml-auto flex items-center gap-2 sm:gap-3">
        <ConnectionStatus />
        <Clock />
        <Separator orientation="vertical" className="hidden h-6 sm:block" />
        <NotificationsSheet />
        <ThemeToggle />
      </div>
    </header>
  )
}
