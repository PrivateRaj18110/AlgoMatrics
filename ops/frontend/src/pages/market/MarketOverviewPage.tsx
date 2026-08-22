import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/layout/Panel'
import { MetricCard } from '@/components/cards/MetricCard'
import { StrategyCard } from '@/components/cards/StrategyCard'
import { QueryState } from '@/components/common/QueryState'
import { EmptyState } from '@/components/common/EmptyState'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { EquityCurveChart } from '@/components/charts/EquityCurveChart'
import { CategoryBarChart } from '@/components/charts/CategoryBarChart'
import { useStrategies } from '@/hooks/useStrategies'
import { useTrades } from '@/hooks/useTrades'
import { useMarket } from '@/providers/market'
import type { KpiMetric } from '@/types'
import { marketPath } from '@/components/navigation/navConfig'
import { bySymbol, equitySeries, summarise } from './marketDerivations'

export default function MarketOverviewPage() {
  const { market, meta, compactMoney, money } = useMarket()
  const strategies = useStrategies(market)
  const trades = useTrades(market)

  const summary = useMemo(
    () => (strategies.data && trades.data ? summarise(strategies.data, trades.data) : null),
    [strategies.data, trades.data],
  )
  const equity = useMemo(() => (trades.data ? equitySeries(trades.data) : []), [trades.data])
  const symbolPnl = useMemo(
    () => (trades.data ? bySymbol(trades.data).map((s) => ({ label: s.key, value: s.netPnl })) : []),
    [trades.data],
  )

  const kpis: KpiMetric[] = summary
    ? [
        { id: 'net_pnl', label: 'Net PnL', value: summary.netPnl, format: 'currency' },
        { id: 'realized', label: 'Realized', value: summary.realizedPnl, format: 'currency' },
        { id: 'unrealized', label: 'Unrealized', value: summary.unrealizedPnl, format: 'currency' },
        { id: 'open_pos', label: 'Open Positions', value: summary.openPositions, format: 'number' },
        { id: 'win_rate', label: 'Win Rate', value: summary.winRate, format: 'percent' },
        { id: 'profit_factor', label: 'Profit Factor', value: summary.profitFactor, format: 'ratio' },
        { id: 'trades', label: 'Total Trades', value: summary.totalTrades, format: 'number' },
        {
          id: 'strategies',
          label: 'Strategies',
          value: summary.onlineStrategies,
          format: 'number',
        },
      ]
    : []

  return (
    <div className="space-y-5">
      <PageHeader
        title={`${meta.label} · Overview`}
        description={`${meta.exchanges.join(' · ')}  ·  ${meta.session}  ·  Settled in ${meta.currency}`}
        actions={
          <Badge variant="muted" className="tabular">
            {meta.currencySymbol} {meta.currency}
          </Badge>
        }
      />

      {/* KPI band */}
      <QueryState
        query={strategies}
        loading={
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        }
      >
        {() => (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
            {kpis.map((kpi) => (
              <MetricCard key={kpi.id} metric={kpi} market={market} />
            ))}
          </div>
        )}
      </QueryState>

      {/* Equity + asset breakdown */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel
          title="Realized Equity Curve"
          subtitle={summary ? `Net after-cost: ${money(summary.realizedPnl, { signed: true })}` : undefined}
          className="lg:col-span-2"
        >
          {equity.length ? (
            <EquityCurveChart
              data={equity}
              height={260}
              valueFormatter={(v) => money(v)}
              tickFormatter={(v) => compactMoney(v)}
            />
          ) : (
            <EmptyState title="No closed trades yet" description="The equity curve builds from closed trades." />
          )}
        </Panel>

        <Panel title="Net PnL by Asset">
          {symbolPnl.length ? (
            <CategoryBarChart
              data={symbolPnl}
              name="Net PnL"
              height={260}
              valueFormatter={(v) => compactMoney(v)}
            />
          ) : (
            <EmptyState title="No assets traded" description="Asset performance appears once trades arrive." />
          )}
        </Panel>
      </div>

      {/* Top strategies */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Strategies
          </h2>
          <Button asChild variant="ghost" size="sm" className="h-7 gap-1 text-xs text-muted-foreground">
            <Link to={marketPath(market, 'strategies')}>
              View all <ArrowRight className="size-3.5" />
            </Link>
          </Button>
        </div>
        <QueryState
          query={strategies}
          loading={
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-60" />
              ))}
            </div>
          }
        >
          {(data) =>
            data.length === 0 ? (
              <EmptyState title="No strategies in this market" description="Deploy a strategy to see it here." />
            ) : (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {data.slice(0, 6).map((s) => (
                  <StrategyCard key={s.id} strategy={s} />
                ))}
              </div>
            )
          }
        </QueryState>
      </section>
    </div>
  )
}
