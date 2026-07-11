import { useClock } from '@/hooks/useClock'
import { cn } from '@/utils/cn'

/** Live UTC + local wall clock for the top bar. */
export function Clock({ className }: { className?: string }) {
  const now = useClock()
  const local = now.toLocaleTimeString('en-GB', { hour12: false })
  const utc = now.toLocaleTimeString('en-GB', { hour12: false, timeZone: 'UTC' })
  const date = now.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })

  return (
    <div className={cn('hidden items-center gap-3 md:flex', className)}>
      <div className="text-right leading-tight">
        <p className="tabular text-sm font-medium">{local}</p>
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{date}</p>
      </div>
      <div className="hidden text-right leading-tight lg:block">
        <p className="tabular text-sm font-medium text-muted-foreground">{utc}</p>
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">UTC</p>
      </div>
    </div>
  )
}
