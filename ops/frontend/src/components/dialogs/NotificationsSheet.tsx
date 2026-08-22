import { useMemo, useState } from 'react'
import { Bell } from 'lucide-react'
import { Link } from 'react-router-dom'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
  SheetClose,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { AlertRow } from '@/components/widgets/AlertRow'
import { EmptyState } from '@/components/common/EmptyState'
import { useAlerts } from '@/hooks/useAlerts'

/** Notification bell + slide-over showing the latest alerts. */
export function NotificationsSheet() {
  const [open, setOpen] = useState(false)
  const { data: alerts = [] } = useAlerts()
  const unacknowledged = useMemo(() => alerts.filter((a) => !a.acknowledged).length, [alerts])

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative size-9 text-muted-foreground"
          aria-label={`Notifications (${unacknowledged} unread)`}
        >
          <Bell className="size-4.5" />
          {unacknowledged > 0 && (
            <span className="absolute right-1.5 top-1.5 flex size-4 items-center justify-center rounded-full bg-danger text-[9px] font-semibold text-danger-foreground">
              {unacknowledged > 9 ? '9+' : unacknowledged}
            </span>
          )}
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="p-0">
        <SheetHeader className="border-b border-border pb-4">
          <SheetTitle className="flex items-center gap-2">
            <Bell className="size-4" />
            Notifications
            {unacknowledged > 0 && (
              <span className="rounded-full bg-danger/15 px-2 py-0.5 text-xs font-medium text-danger">
                {unacknowledged} new
              </span>
            )}
          </SheetTitle>
        </SheetHeader>

        <ScrollArea className="h-[calc(100%-7.5rem)]">
          <div className="space-y-2 p-4">
            {alerts.length === 0 ? (
              <EmptyState icon={Bell} title="All clear" description="No alerts at the moment." />
            ) : (
              alerts.map((alert) => <AlertRow key={alert.id} alert={alert} />)
            )}
          </div>
        </ScrollArea>

        <div className="border-t border-border p-3">
          <SheetClose asChild>
            <Button asChild variant="outline" className="w-full">
              <Link to="/alerts">Open alert center</Link>
            </Button>
          </SheetClose>
        </div>
      </SheetContent>
    </Sheet>
  )
}
