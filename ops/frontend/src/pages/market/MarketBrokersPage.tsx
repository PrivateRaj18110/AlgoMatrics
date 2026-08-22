import { useMemo } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/layout/Panel'
import { PnlValue } from '@/components/common/PnlValue'
import { QueryState } from '@/components/common/QueryState'
import { EmptyState } from '@/components/common/EmptyState'
import { Skeleton } from '@/components/ui/skeleton'
import { CategoryBarChart } from '@/components/charts/CategoryBarChart'
import { useTrades } from '@/hooks/useTrades'
import { useMarket } from '@/providers/market'
import { formatLatency, formatPercent } from '@/utils/format'
import { byBroker } from './marketDerivations'

export default function MarketBrokersPage() {
  const { market, meta, compactMoney } = useMarket()
  const query = useTrades(market)

  const rows = useMemo(() => (query.data ? byBroker(query.data) : []), [query.data])
  const bars = rows.map((r) => ({ label: r.key, value: r.netPnl }))

  return (
    <div className="space-y-5">
      <PageHeader
        title={`${meta.label} · Brokers`}
        description={`Execution venues for this market — ${meta.exchanges.join(', ')}.`}
      />

      <QueryState query={query} loading={<Skeleton className="h-[420px] w-full" />}>
        {() =>
          rows.length === 0 ? (
            <EmptyState title="No broker activity" description="Broker performance appears once trades route." />
          ) : (
            <div className="grid gap-4 lg:grid-cols-5">
              <Panel title="Net PnL by Broker" className="lg:col-span-3">
                <CategoryBarChart
                  data={bars}
                  name="Net PnL"
                  height={300}
                  valueFormatter={(v) => compactMoney(v)}
                />
              </Panel>
              <Panel title="Broker Performance" className="lg:col-span-2" flush bodyClassName="overflow-auto">
                <table className="w-full text-sm">
                  <thead className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    <tr className="border-b border-border">
                      <th className="px-4 py-2 text-left font-medium">Broker</th>
                      <th className="px-4 py-2 text-right font-medium">Trades</th>
                      <th className="px-4 py-2 text-right font-medium">Win %</th>
                      <th className="px-4 py-2 text-right font-medium">Latency</th>
                      <th className="px-4 py-2 text-right font-medium">Net PnL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.key} className="border-b border-border/60">
                        <td className="px-4 py-2 truncate font-medium">{r.key}</td>
                        <td className="px-4 py-2 text-right tabular">{r.trades}</td>
                        <td className="px-4 py-2 text-right tabular">{formatPercent(r.winRate)}</td>
                        <td className="px-4 py-2 text-right tabular">{formatLatency(r.avgLatencyMs)}</td>
                        <td className="px-4 py-2 text-right">
                          <PnlValue value={r.netPnl} market={market} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Panel>
            </div>
          )
        }
      </QueryState>
    </div>
  )
}
