import { lazy, Suspense, useDeferredValue, useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { PnlValue } from '@/components/common/PnlValue'
import { QueryState } from '@/components/common/QueryState'
import { EmptyState } from '@/components/common/EmptyState'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useTrades } from '@/hooks/useTrades'
import { useMarket } from '@/providers/market'

const TradesTable = lazy(() =>
  import('@/components/tables/TradesTable').then((m) => ({ default: m.TradesTable })),
)

export default function ClosedTradesPage() {
  const { market, meta } = useMarket()
  const query = useTrades(market)
  const [search, setSearch] = useState('')
  const deferredSearch = useDeferredValue(search)

  const closed = useMemo(
    () => (query.data ?? []).filter((t) => t.status !== 'open'),
    [query.data],
  )
  const stats = useMemo(() => {
    const settled = closed.filter((t) => t.status === 'closed')
    const realised = settled.reduce((s, t) => s + t.pnl, 0)
    const wins = settled.filter((t) => t.pnl > 0).length
    return {
      total: closed.length,
      realised,
      winRate: settled.length ? Math.round((wins / settled.length) * 100) : 0,
      avg: settled.length ? Math.round(realised / settled.length) : 0,
    }
  }, [closed])

  return (
    <div className="space-y-5">
      <PageHeader
        title={`${meta.label} · Closed Trades`}
        description="Historical execution record across every strategy, broker and machine in this market."
        actions={
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search symbol, strategy, broker…"
              className="w-64 pl-8"
            />
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Closed Trades" value={String(stats.total)} />
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Realised PnL</p>
          <PnlValue value={stats.realised} market={market} className="mt-2 block text-2xl" />
        </Card>
        <Stat label="Win Rate" value={`${stats.winRate}%`} />
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Avg Trade</p>
          <PnlValue value={stats.avg} market={market} className="mt-2 block text-2xl" />
        </Card>
      </div>

      <QueryState query={query} loading={<Skeleton className="h-[520px] w-full" />}>
        {() =>
          closed.length === 0 ? (
            <EmptyState title="No closed trades" description="Settled trades for this market will appear here." />
          ) : (
            <div className="h-[calc(100dvh-21rem)] min-h-[460px] w-full">
              <Suspense fallback={<Skeleton className="h-full w-full" />}>
                <TradesTable trades={closed} quickFilterText={deferredSearch} height="100%" />
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
