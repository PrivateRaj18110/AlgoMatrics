import { useMemo } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { BrokerCard } from '@/components/cards/BrokerCard'
import { QueryState } from '@/components/common/QueryState'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useBrokers } from '@/hooks/useBrokers'
import { formatCompactCurrency } from '@/utils/format'
import type { Broker } from '@/types'

function summarise(brokers: Broker[]) {
  return {
    total: brokers.length,
    connected: brokers.filter((b) => b.connection === 'online').length,
    equity: brokers.reduce((s, b) => s + b.equity, 0),
    openPositions: brokers.reduce((s, b) => s + b.openPositions, 0),
    rejected: brokers.reduce((s, b) => s + b.rejectedOrders, 0),
  }
}

export default function BrokersPage() {
  const query = useBrokers()
  const stats = useMemo(() => (query.data ? summarise(query.data) : null), [query.data])

  return (
    <div className="space-y-5">
      <PageHeader
        title="Brokers"
        description="Connectivity, balances and order flow across every liquidity venue. Scales to an unlimited roster."
      />

      {stats && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <Stat label="Brokers" value={String(stats.total)} />
          <Stat label="Connected" value={`${stats.connected}/${stats.total}`} />
          <Stat label="Total Equity" value={formatCompactCurrency(stats.equity)} />
          <Stat label="Open Positions" value={String(stats.openPositions)} />
          <Stat label="Rejected Orders" value={String(stats.rejected)} />
        </div>
      )}

      <QueryState
        query={query}
        loading={
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-80" />
            ))}
          </div>
        }
      >
        {(data) => (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {data.map((b) => (
              <BrokerCard key={b.id} broker={b} />
            ))}
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
