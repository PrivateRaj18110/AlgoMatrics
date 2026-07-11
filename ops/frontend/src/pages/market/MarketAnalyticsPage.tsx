import { useMemo } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/layout/Panel'
import { Card } from '@/components/ui/card'
import { PnlValue } from '@/components/common/PnlValue'
import { QueryState } from '@/components/common/QueryState'
import { EmptyState } from '@/components/common/EmptyState'
import { Skeleton } from '@/components/ui/skeleton'
import { EquityCurveChart } from '@/components/charts/EquityCurveChart'
import { CategoryBarChart } from '@/components/charts/CategoryBarChart'
import { useTrades } from '@/hooks/useTrades'
import { useMarket } from '@/providers/market'
import { formatPercent } from '@/utils/format'
import { bySymbol, equitySeries, summarise } from './marketDerivations'

export default function MarketAnalyticsPage() {
  const { market, meta, money, compactMoney } = useMarket()
  const query = useTrades(market)

  const equity = useMemo(() => (query.data ? equitySeries(query.data) : []), [query.data])
  const symbolPnl = useMemo(
    () => (query.data ? bySymbol(query.data).map((s) => ({ label: s.key, value: s.netPnl })) : []),
    [query.data],
  )
  const stats = useMemo(() => {
    if (!query.data) return null
    const s = summarise([], query.data)
    const closed = query.data.filter((t) => t.status === 'closed')
    const best = closed.reduce((m, t) => Math.max(m, t.pnl), 0)
    const worst = closed.reduce((m, t) => Math.min(m, t.pnl), 0)
    return { ...s, best, worst }
  }, [query.data])

  return (
    <div className="space-y-5">
      <PageHeader
        title={`${meta.label} · Analytics`}
        description="Performance attribution derived from this market's closed trades."
      />

      <QueryState
        query={query}
        loading={
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        }
      >
        {() =>
          stats && (
            <>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
                <Stat label="Win Rate" value={formatPercent(stats.winRate)} />
                <Stat label="Profit Factor" value={stats.profitFactor.toFixed(2)} />
                <Card className="p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Expectancy</p>
                  <PnlValue value={stats.expectancy} market={market} className="mt-2 block text-xl" />
                </Card>
                <Card className="p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Best Trade</p>
                  <PnlValue value={stats.best} market={market} className="mt-2 block text-xl" />
                </Card>
                <Card className="p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Worst Trade</p>
                  <PnlValue value={stats.worst} market={market} className="mt-2 block text-xl" />
                </Card>
                <Stat label="Closed Trades" value={String(stats.closedTrades)} />
              </div>

              <div className="grid gap-4 lg:grid-cols-3">
                <Panel
                  title="Realized Equity Curve"
                  subtitle={`Net: ${money(stats.realizedPnl, { signed: true })}`}
                  className="lg:col-span-2"
                >
                  {equity.length ? (
                    <EquityCurveChart
                      data={equity}
                      height={280}
                      valueFormatter={(v) => money(v)}
                      tickFormatter={(v) => compactMoney(v)}
                    />
                  ) : (
                    <EmptyState title="No closed trades" description="The curve builds from closed trades." />
                  )}
                </Panel>
                <Panel title="Net PnL by Asset">
                  {symbolPnl.length ? (
                    <CategoryBarChart
                      data={symbolPnl}
                      name="Net PnL"
                      height={280}
                      valueFormatter={(v) => compactMoney(v)}
                    />
                  ) : (
                    <EmptyState title="No assets" description="Asset attribution appears with trades." />
                  )}
                </Panel>
              </div>
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
