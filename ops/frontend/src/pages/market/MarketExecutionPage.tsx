import { useMemo } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/layout/Panel'
import { Card } from '@/components/ui/card'
import { QueryState } from '@/components/common/QueryState'
import { EmptyState } from '@/components/common/EmptyState'
import { Skeleton } from '@/components/ui/skeleton'
import { CategoryBarChart } from '@/components/charts/CategoryBarChart'
import { useTrades } from '@/hooks/useTrades'
import { useMarket } from '@/providers/market'
import { formatLatency, formatPercent } from '@/utils/format'
import { byBroker, latencyStats } from './marketDerivations'

export default function MarketExecutionPage() {
  const { market, meta } = useMarket()
  const query = useTrades(market)

  const stats = useMemo(() => (query.data ? latencyStats(query.data) : null), [query.data])
  const latencyByBroker = useMemo(
    () => (query.data ? byBroker(query.data).map((b) => ({ label: b.key, value: b.avgLatencyMs })) : []),
    [query.data],
  )

  return (
    <div className="space-y-5">
      <PageHeader
        title={`${meta.label} · Execution`}
        description="Round-trip latency, fill quality and venue performance for this market."
      />

      <QueryState
        query={query}
        loading={
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        }
      >
        {() =>
          stats && (
            <>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
                <Stat label="Avg Latency" value={formatLatency(stats.avg)} />
                <Stat label="p50 Latency" value={formatLatency(stats.p50)} />
                <Stat label="p95 Latency" value={formatLatency(stats.p95)} />
                <Stat label="Max Latency" value={formatLatency(stats.max)} />
                <Stat label="Fill Rate" value={formatPercent(stats.fillRate)} />
              </div>

              <Panel title="Average Latency by Broker">
                {latencyByBroker.length ? (
                  <CategoryBarChart
                    data={latencyByBroker}
                    name="Avg Latency"
                    height={300}
                    valueFormatter={(v) => formatLatency(v)}
                  />
                ) : (
                  <EmptyState title="No execution data" description="Latency appears once orders route." />
                )}
              </Panel>
            </>
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
      <p className="mt-2 text-xl font-semibold tabular">{value}</p>
    </Card>
  )
}
