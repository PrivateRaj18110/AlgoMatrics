import { memo } from 'react'
import { Server } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { StatusBadge } from '@/components/common/StatusBadge'
import { PnlValue } from '@/components/common/PnlValue'
import { Sparkline } from '@/components/widgets/Sparkline'
import type { Strategy } from '@/types'
import { cn } from '@/utils/cn'
import { formatLatency, formatPercent, formatRelativeTime } from '@/utils/format'
import { LATENCY_THRESHOLDS } from '@/utils/constants'

interface StrategyCardProps {
  strategy: Strategy
  className?: string
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="space-y-0.5">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn('text-sm font-semibold tabular', tone ?? 'text-foreground')}>{value}</p>
    </div>
  )
}

/** Reusable strategy card. Designed to scale to an unlimited strategy roster. */
export const StrategyCard = memo(function StrategyCard({ strategy, className }: StrategyCardProps) {
  const latencyTone =
    strategy.avgLatencyMs >= LATENCY_THRESHOLDS.danger
      ? 'text-danger'
      : strategy.avgLatencyMs >= LATENCY_THRESHOLDS.warning
        ? 'text-warning'
        : 'text-foreground'

  return (
    <Card className={cn('flex flex-col gap-3 p-4', className)}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="truncate text-sm font-semibold">{strategy.name}</p>
            <Badge variant="muted" className="shrink-0">
              {strategy.code}
            </Badge>
          </div>
          <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Server className="size-3.5" />
            <span className="truncate">{strategy.machineName}</span>
            <span>·</span>
            <span className="truncate">{strategy.broker}</span>
          </p>
        </div>
        <StatusBadge status={strategy.status} />
      </div>

      {/* Sparkline */}
      <Sparkline data={strategy.sparkline} height={44} />

      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-0.5">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Today PnL</p>
          <PnlValue value={strategy.todayPnl} market={strategy.market} className="text-sm" />
        </div>
        <Stat label="Trades" value={String(strategy.todayTrades)} />
        <Stat label="Open" value={String(strategy.openPositions)} />
        <Stat label="Win Rate" value={formatPercent(strategy.winRate)} />
        <Stat label="Profit F." value={strategy.profitFactor.toFixed(2)} />
        <Stat label="Latency" value={formatLatency(strategy.avgLatencyMs)} tone={latencyTone} />
      </div>

      {/* Footer */}
      <div className="mt-auto flex flex-wrap items-center gap-1 border-t border-border pt-2.5 text-[11px] text-muted-foreground">
        {strategy.symbols.map((s) => (
          <span key={s} className="rounded bg-muted px-1.5 py-0.5 tabular">
            {s}
          </span>
        ))}
        <span className="ml-auto">
          {strategy.status === 'offline'
            ? 'No heartbeat'
            : `Heartbeat ${formatRelativeTime(strategy.lastHeartbeat)}`}
        </span>
      </div>
    </Card>
  )
})
