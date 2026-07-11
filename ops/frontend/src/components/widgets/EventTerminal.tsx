import { memo } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { EmptyState } from '@/components/common/EmptyState'
import type { EventCategory, Severity, SystemEvent } from '@/types'
import { cn } from '@/utils/cn'
import { formatTime } from '@/utils/format'

/** Per-category accent (the left tag colour). */
const CATEGORY_STYLE: Record<EventCategory, string> = {
  trade: 'text-chart-2 bg-success/10',
  strategy: 'text-primary bg-primary/10',
  machine: 'text-chart-4 bg-[#a855f7]/10',
  broker: 'text-chart-5 bg-[#06b6d4]/10',
  system: 'text-muted-foreground bg-muted',
  database: 'text-warning bg-warning/10',
  risk: 'text-danger bg-danger/10',
}

/** Severity drives the message colour. */
const SEVERITY_TEXT: Record<Severity, string> = {
  info: 'text-foreground',
  warning: 'text-warning',
  critical: 'text-danger',
}

interface EventTerminalProps {
  events: SystemEvent[]
  maxHeight?: number | string
  className?: string
}

/**
 * Bloomberg-style live event terminal: monospace, newest-first, severity-
 * coloured and scrollable. New events stream in via the realtime feed.
 */
export const EventTerminal = memo(function EventTerminal({
  events,
  maxHeight = '100%',
  className,
}: EventTerminalProps) {
  if (events.length === 0) {
    return <EmptyState title="No events" description="The event stream is quiet right now." />
  }

  return (
    <ScrollArea className={cn('h-full', className)} style={{ maxHeight }}>
      <div className="divide-y divide-border/60 font-mono text-xs">
        {events.map((e) => (
          <div
            key={e.id}
            className="flex items-start gap-2 px-3 py-1.5 transition-colors hover:bg-accent/40"
          >
            <span className="shrink-0 tabular text-muted-foreground">{formatTime(e.time)}</span>
            <span
              className={cn(
                'w-16 shrink-0 rounded px-1 text-center text-[10px] font-semibold uppercase tracking-wide',
                CATEGORY_STYLE[e.category],
              )}
            >
              {e.category}
            </span>
            <span className="w-32 shrink-0 truncate text-muted-foreground">{e.source}</span>
            <span className={cn('min-w-0 flex-1', SEVERITY_TEXT[e.severity])}>{e.message}</span>
          </div>
        ))}
      </div>
    </ScrollArea>
  )
})
