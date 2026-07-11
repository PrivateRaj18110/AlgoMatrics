import { memo } from 'react'
import { Network } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { StatusBadge } from '@/components/common/StatusBadge'
import { StatusDot } from '@/components/common/StatusDot'
import { Sparkline } from '@/components/widgets/Sparkline'
import type { Broker } from '@/types'
import { cn } from '@/utils/cn'
import { formatCompactCurrency, formatLatency, formatRelativeTime } from '@/utils/format'
import { LATENCY_THRESHOLDS } from '@/utils/constants'

function Field({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="space-y-0.5">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn('text-sm font-semibold tabular', tone ?? 'text-foreground')}>{value}</p>
    </div>
  )
}

/** Broker connection card: balance, margin, order flow and gateway health. */
export const BrokerCard = memo(function BrokerCard({ broker }: { broker: Broker }) {
  const offline = broker.connection === 'offline'
  const pingTone =
    broker.pingMs >= LATENCY_THRESHOLDS.danger
      ? 'text-danger'
      : broker.pingMs >= LATENCY_THRESHOLDS.warning
        ? 'text-warning'
        : 'text-foreground'

  return (
    <Card className="flex flex-col gap-3 p-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <Network className="size-4.5" />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{broker.name}</p>
            <p className="truncate text-xs text-muted-foreground tabular">{broker.server}</p>
          </div>
        </div>
        <StatusBadge status={broker.connection} />
      </div>

      {/* Ping sparkline */}
      <Sparkline data={broker.pingHistory} color="var(--color-chart-5)" height={36} />

      {/* Financials */}
      <div className="grid grid-cols-3 gap-3">
        <Field label="Balance" value={formatCompactCurrency(broker.balance)} />
        <Field label="Equity" value={formatCompactCurrency(broker.equity)} />
        <Field label="Free Margin" value={formatCompactCurrency(broker.freeMargin)} />
        <Field label="Margin" value={formatCompactCurrency(broker.margin)} />
        <Field
          label="Margin Lvl"
          value={broker.marginLevelPct ? `${broker.marginLevelPct}%` : '—'}
        />
        <Field label="Leverage" value={`1:${broker.leverage}`} />
        <Field label="Spread" value={`${broker.spreadPips} pips`} />
        <Field label="Ping" value={offline ? '—' : formatLatency(broker.pingMs)} tone={pingTone} />
        <Field label="Account" value={broker.account} />
      </div>

      {/* Order flow */}
      <div className="grid grid-cols-3 gap-1.5">
        <OrderStat label="Open" value={broker.openPositions} />
        <OrderStat label="Pending" value={broker.pendingOrders} />
        <OrderStat label="Rejected" value={broker.rejectedOrders} tone={broker.rejectedOrders > 0 ? 'text-warning' : undefined} />
      </div>

      {/* Footer */}
      <div className="mt-auto flex items-center justify-between border-t border-border pt-2.5 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <StatusDot status={broker.connection} />
          {offline ? 'Disconnected' : `Synced ${formatRelativeTime(broker.lastSync)}`}
        </span>
      </div>
    </Card>
  )
})

function OrderStat({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="rounded-md bg-background/40 px-2 py-1.5 text-center">
      <p className={cn('text-base font-semibold tabular', tone ?? 'text-foreground')}>{value}</p>
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
    </div>
  )
}
