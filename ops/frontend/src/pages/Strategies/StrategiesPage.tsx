import { useMemo, useState } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { StrategyCard } from '@/components/cards/StrategyCard'
import { PnlValue } from '@/components/common/PnlValue'
import { QueryState } from '@/components/common/QueryState'
import { EmptyState } from '@/components/common/EmptyState'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useStrategies } from '@/hooks/useStrategies'
import { useMarket } from '@/providers/market'
import type { Status, Strategy } from '@/types'

type Filter = 'all' | Status

function summarise(strategies: Strategy[]) {
  return {
    total: strategies.length,
    online: strategies.filter((s) => s.status === 'online').length,
    todayPnl: strategies.reduce((s, x) => s + x.todayPnl, 0),
    openPositions: strategies.reduce((s, x) => s + x.openPositions, 0),
  }
}

export default function StrategiesPage() {
  const { market, meta } = useMarket()
  const query = useStrategies(market)
  const [filter, setFilter] = useState<Filter>('all')

  const stats = useMemo(() => (query.data ? summarise(query.data) : null), [query.data])
  const filtered = useMemo(
    () => (query.data ?? []).filter((s) => filter === 'all' || s.status === filter),
    [query.data, filter],
  )

  return (
    <div className="space-y-5">
      <PageHeader
        title={`${meta.label} · Strategies`}
        description="Monitor every algo instance in this market. Scales to an unlimited roster."
        actions={
          <Tabs value={filter} onValueChange={(v) => setFilter(v as Filter)}>
            <TabsList>
              <TabsTrigger value="all">All</TabsTrigger>
              <TabsTrigger value="online">Online</TabsTrigger>
              <TabsTrigger value="degraded">Degraded</TabsTrigger>
              <TabsTrigger value="offline">Offline</TabsTrigger>
            </TabsList>
          </Tabs>
        }
      />

      {/* Summary */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <SummaryStat label="Strategies" value={String(stats.total)} />
          <SummaryStat label="Online" value={`${stats.online}/${stats.total}`} />
          <Card className="p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Today PnL</p>
            <PnlValue value={stats.todayPnl} market={market} className="mt-2 block text-2xl" />
          </Card>
          <SummaryStat label="Open Positions" value={String(stats.openPositions)} />
        </div>
      )}

      <QueryState
        query={query}
        loading={
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-60" />
            ))}
          </div>
        }
      >
        {() =>
          filtered.length === 0 ? (
            <EmptyState title="No strategies match this filter" description="Try a different status filter." />
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {filtered.map((s) => (
                <StrategyCard key={s.id} strategy={s} />
              ))}
            </div>
          )
        }
      </QueryState>
    </div>
  )
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-2 text-2xl font-semibold tabular">{value}</p>
    </Card>
  )
}
