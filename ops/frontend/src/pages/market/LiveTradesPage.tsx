import { lazy, Suspense, useMemo } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { PnlValue } from '@/components/common/PnlValue'
import { QueryState } from '@/components/common/QueryState'
import { EmptyState } from '@/components/common/EmptyState'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useTrades } from '@/hooks/useTrades'
import { useMarket } from '@/providers/market'
import type { Trade } from '@/types'

const TradesTable = lazy(() =>
  import('@/components/tables/TradesTable').then((m) => ({ default: m.TradesTable })),
)

export default function LiveTradesPage() {
  const { market, meta, compactMoney } = useMarket()
  const query = useTrades(market)

  const open = useMemo(() => (query.data ?? []).filter((t) => t.status === 'open'), [query.data])
  const stats = useMemo(() => {
    const floating = open.reduce((s, t) => s + t.pnl, 0)
    const exposure = open.reduce((s, t) => s + Math.abs(t.entry * t.quantity), 0)
    const longs = open.filter((t) => t.direction === 'long').length
    return { count: open.length, floating, exposure, longs, shorts: open.length - longs }
  }, [open])

  return (
    <div className="space-y-5">
      <PageHeader
        title={`${meta.label} · Live Trades`}
        description="Open positions with live floating PnL and exposure."
        actions={<Badge variant="muted">{meta.session}</Badge>}
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Open Positions" value={String(stats.count)} />
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Floating PnL</p>
          <PnlValue value={stats.floating} market={market} className="mt-2 block text-2xl" />
        </Card>
        <Stat label="Gross Exposure" value={compactMoney(stats.exposure)} />
        <Stat label="Long / Short" value={`${stats.longs} / ${stats.shorts}`} />
      </div>

      <QueryState query={query} loading={<Skeleton className="h-[480px] w-full" />}>
        {() =>
          open.length === 0 ? (
            <EmptyState
              title="No live positions"
              description="Open trades for this market will stream in here."
            />
          ) : (
            <div className="h-[calc(100dvh-21rem)] min-h-[420px] w-full">
              <Suspense fallback={<Skeleton className="h-full w-full" />}>
                <TradesTable trades={open} height="100%" />
              </Suspense>
            </div>
          )
        }
      </QueryState>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-2 text-2xl font-semibold tabular">{value}</p>
    </Card>
  )
}
