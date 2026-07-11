import { lazy, Suspense, useDeferredValue, useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { PnlValue } from '@/components/common/PnlValue'
import { QueryState } from '@/components/common/QueryState'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useTrades } from '@/hooks/useTrades'
import type { Trade } from '@/types'

// The grid (AG Grid) is heavy — load it only when this route is opened.
const TradesTable = lazy(() =>
  import('@/components/tables/TradesTable').then((m) => ({ default: m.TradesTable })),
)

function summarise(trades: Trade[]) {
  const closed = trades.filter((t) => t.status === 'closed')
  const open = trades.filter((t) => t.status === 'open')
  const realised = closed.reduce((s, t) => s + t.pnl, 0)
  const wins = closed.filter((t) => t.pnl > 0).length
  return {
    total: trades.length,
    open: open.length,
    realised,
    winRate: closed.length ? Math.round((wins / closed.length) * 100) : 0,
  }
}

export default function TradesPage() {
  const query = useTrades()
  const [search, setSearch] = useState('')
  const deferredSearch = useDeferredValue(search)

  const stats = useMemo(() => (query.data ? summarise(query.data) : null), [query.data])

  return (
    <div className="space-y-5">
      <PageHeader
        title="Trade Blotter"
        description="Full execution history across all strategies, machines and brokers."
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

      {stats && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Total Trades" value={String(stats.total)} />
          <Stat label="Open" value={String(stats.open)} />
          <Card className="p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Realised PnL</p>
            <PnlValue value={stats.realised} className="mt-2 block text-2xl" />
          </Card>
          <Stat label="Win Rate" value={`${stats.winRate}%`} />
        </div>
      )}

      <QueryState query={query} loading={<Skeleton className="h-[560px] w-full" />}>
        {(data) => (
          <div className="h-[calc(100dvh-19rem)] min-h-[460px] w-full">
            <Suspense fallback={<Skeleton className="h-full w-full" />}>
              <TradesTable trades={data} quickFilterText={deferredSearch} height="100%" />
            </Suspense>
          </div>
        )}
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
