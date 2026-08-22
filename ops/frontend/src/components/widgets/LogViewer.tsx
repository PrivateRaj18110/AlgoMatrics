import { memo } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { EmptyState } from '@/components/common/EmptyState'
import type { LogEntry, LogLevel } from '@/types'
import { cn } from '@/utils/cn'
import { formatTime } from '@/utils/format'

const LEVEL_STYLE: Record<LogLevel, { text: string; tag: string }> = {
  debug: { text: 'text-muted-foreground', tag: 'bg-muted text-muted-foreground' },
  info: { text: 'text-foreground', tag: 'bg-primary/10 text-primary' },
  warn: { text: 'text-warning', tag: 'bg-warning/10 text-warning' },
  error: { text: 'text-danger', tag: 'bg-danger/10 text-danger' },
}

interface LogViewerProps {
  logs: LogEntry[]
  maxHeight?: number | string
  className?: string
}

/** Terminal log stream — monospace, level-coloured, newest first. */
export const LogViewer = memo(function LogViewer({
  logs,
  maxHeight = '100%',
  className,
}: LogViewerProps) {
  if (logs.length === 0) {
    return <EmptyState title="No log lines" description="Nothing logged for this stream yet." />
  }

  return (
    <ScrollArea className={cn('h-full', className)} style={{ maxHeight }}>
      <div className="divide-y divide-border/50 font-mono text-xs">
        {logs.map((l) => {
          const style = LEVEL_STYLE[l.level]
          return (
            <div key={l.id} className="flex items-start gap-2 px-3 py-1 hover:bg-accent/40">
              <span className="shrink-0 tabular text-muted-foreground">{formatTime(l.time)}</span>
              <span
                className={cn(
                  'w-12 shrink-0 rounded px-1 text-center text-[10px] font-semibold uppercase',
                  style.tag,
                )}
              >
                {l.level}
              </span>
              <span className="w-32 shrink-0 truncate text-muted-foreground">{l.logger}</span>
              <span className={cn('min-w-0 flex-1 break-words', style.text)}>{l.message}</span>
            </div>
          )
        })}
      </div>
    </ScrollArea>
  )
})
