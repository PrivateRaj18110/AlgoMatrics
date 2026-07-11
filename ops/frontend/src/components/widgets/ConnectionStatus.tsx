import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { StatusDot } from '@/components/common/StatusDot'
import { useConnection } from '@/hooks/useConnection'
import { USE_MOCK } from '@/services'
import { describeStatus } from '@/utils/status'
import { formatLatency, formatRelativeTime } from '@/utils/format'
import { cn } from '@/utils/cn'

/** Live data-feed connection indicator for the top bar. */
export function ConnectionStatus({ className }: { className?: string }) {
  const conn = useConnection()
  const desc = describeStatus(conn.status)

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className={cn(
            'flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5',
            className,
          )}
        >
          <StatusDot status={conn.status} />
          <span className={cn('text-xs font-medium', desc.text)}>
            {USE_MOCK ? 'Mock Feed' : 'Live Feed'}
          </span>
          <span className="hidden text-xs text-muted-foreground tabular sm:inline">
            {formatLatency(conn.latencyMs)}
          </span>
        </div>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="space-y-0.5">
        <p className="font-medium">Data feed: {desc.label}</p>
        <p className="text-muted-foreground">Round-trip {formatLatency(conn.latencyMs)}</p>
        <p className="text-muted-foreground">Synced {formatRelativeTime(conn.lastSync)}</p>
        {USE_MOCK && <p className="text-muted-foreground">Source: bundled mock data</p>}
      </TooltipContent>
    </Tooltip>
  )
}
