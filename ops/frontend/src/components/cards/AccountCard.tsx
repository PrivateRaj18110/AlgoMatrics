import { memo } from 'react'
import { Wallet } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { StatusBadge } from '@/components/common/StatusBadge'
import { PnlValue } from '@/components/common/PnlValue'
import { Sparkline } from '@/components/widgets/Sparkline'
import type { Account } from '@/types'
import { cn } from '@/utils/cn'
import { formatCompactCurrency } from '@/utils/format'

const TYPE_VARIANT = {
  live: 'success',
  prop: 'default',
  demo: 'muted',
} as const

function Field({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="space-y-0.5">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn('text-sm font-semibold tabular', tone ?? 'text-foreground')}>{value}</p>
    </div>
  )
}

/** Trading account card: equity curve, balances and live pnl. */
export const AccountCard = memo(function AccountCard({ account }: { account: Account }) {
  return (
    <Card className="flex flex-col gap-3 p-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <Wallet className="size-4.5" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <p className="truncate text-sm font-semibold tabular">{account.label}</p>
              <Badge variant={TYPE_VARIANT[account.type]} className="shrink-0 uppercase">
                {account.type}
              </Badge>
            </div>
            <p className="truncate text-xs text-muted-foreground">
              {account.broker} · {account.currency}
            </p>
          </div>
        </div>
        <StatusBadge status={account.status} />
      </div>

      {/* Equity sparkline */}
      <Sparkline data={account.equityCurve} color="var(--color-chart-1)" height={40} />

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <Field label="Balance" value={formatCompactCurrency(account.balance)} />
        <Field label="Equity" value={formatCompactCurrency(account.equity)} />
        <div className="space-y-0.5">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Today PnL</p>
          <PnlValue value={account.todayPnl} className="text-sm" />
        </div>
        <div className="space-y-0.5">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Open PnL</p>
          <PnlValue value={account.openPnl} className="text-sm" />
        </div>
        <Field label="Margin Lvl" value={`${account.marginLevelPct}%`} />
        <Field label="Leverage" value={`1:${account.leverage}`} />
      </div>

      {/* Footer */}
      <div className="mt-auto flex flex-wrap items-center gap-1 border-t border-border pt-2.5 text-[11px] text-muted-foreground">
        <span>{account.openPositions} open</span>
        <span className="ml-auto flex flex-wrap gap-1">
          {account.strategies.map((s) => (
            <span key={s} className="rounded bg-muted px-1.5 py-0.5 tabular">
              {s}
            </span>
          ))}
        </span>
      </div>
    </Card>
  )
})
