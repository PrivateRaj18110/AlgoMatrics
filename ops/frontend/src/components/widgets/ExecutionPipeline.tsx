import { memo, Fragment } from 'react'
import { ArrowDown } from 'lucide-react'
import type { ExecutionStage } from '@/types'
import { cn } from '@/utils/cn'
import { formatLatency, formatNumber } from '@/utils/format'

const STATUS_RING: Record<ExecutionStage['status'], string> = {
  ok: 'border-success/40 bg-success/5',
  warn: 'border-warning/50 bg-warning/5',
  fail: 'border-danger/50 bg-danger/5',
}

const STATUS_DOT: Record<ExecutionStage['status'], string> = {
  ok: 'bg-success',
  warn: 'bg-warning',
  fail: 'bg-danger',
}

/**
 * Vertical execution pipeline: signal → risk → order → broker → fill → trade.
 * Each node shows its dwell time and throughput; connectors flag drop-offs
 * (risk blocks / rejections).
 */
export const ExecutionPipeline = memo(function ExecutionPipeline({
  stages,
}: {
  stages: ExecutionStage[]
}) {
  return (
    <div className="mx-auto flex max-w-md flex-col">
      {stages.map((stage, i) => (
        <Fragment key={stage.key}>
          <div
            className={cn(
              'flex items-center justify-between gap-3 rounded-lg border px-4 py-2.5',
              STATUS_RING[stage.status],
            )}
          >
            <div className="flex items-center gap-2.5">
              <span className={cn('size-2 rounded-full', STATUS_DOT[stage.status])} />
              <span className="text-sm font-medium">{stage.label}</span>
            </div>
            <div className="flex items-center gap-4 text-xs tabular text-muted-foreground">
              <span title="Orders through this stage">{formatNumber(stage.count)}</span>
              {stage.avgMs > 0 && (
                <span className="font-semibold text-foreground" title="Median dwell time">
                  {formatLatency(stage.avgMs)}
                </span>
              )}
            </div>
          </div>

          {i < stages.length - 1 && (
            <div className="flex items-center justify-center gap-2 py-1 text-muted-foreground">
              <ArrowDown className="size-3.5" />
              {stages[i + 1].dropped > 0 && (
                <span className="text-[11px] text-danger">−{stages[i + 1].dropped} dropped</span>
              )}
            </div>
          )}
        </Fragment>
      ))}
    </div>
  )
})
