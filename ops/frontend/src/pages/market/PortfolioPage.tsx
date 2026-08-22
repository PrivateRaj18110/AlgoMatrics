import { useMemo } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/layout/Panel'
import { Card } from '@/components/ui/card'
import { PnlValue } from '@/components/common/PnlValue'
import { QueryState } from '@/components/common/QueryState'
import { EmptyState } from '@/components/common/EmptyState'
import { Skeleton } from '@/components/ui/skeleton'
import { CategoryBarChart } from '@/components/charts/CategoryBarChart'
import { useStrategies } from '@/hooks/useStrategies'
import { useTrades } from '@/hooks/useTrades'
import { useMarket } from '@/providers/market'
import { formatPercent } from '@/utils/format'
import { byStrategy, bySymbol, summarise } from './marketDerivations'

export default function PortfolioPage() {
  const { market, meta, compactMoney } = useMarket()
  const strategies = useStrategies(market)
  const trades = useTrades(market)

  const ready = strategies.data && trades.data
  const summary = useMemo(
    () => (ready ? summarise(strategies.data!, trades.data!) : null),
    [ready, strategies.data, trades.data],
  )
  const symbols = useMemo(() => (trades.data ? bySymbol(trades.data) : []), [trades.data])
  const strategyRows = useMemo(() => (trades.data ? byStrategy(trades.data) : []), [trades.data])

  const totalExposure = symbols.reduce((s, x) => s + x.exposure, 0)
  const exposureBars = symbols
    .filter((s) => s.exposure > 0)
    .map((s) => ({ label: s.key, value: Math.round(s.exposure) }))

  return (
    <div className="space-y-5">
      <PageHeader
        title={`${meta.label} · Portfolio`}
        description="Capital allocation, exposure and diversification across selected strategies."
      />

      <QueryState
        query={strategies}
        loading={
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        }
      >
        {() =>
          summary && (
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Card className="p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Net PnL</p>
                <PnlValue value={summary.netPnl} market={market} className="mt-2 block text-2xl" />
              </Card>
              <Stat label="Gross Exposure" value={compactMoney(summary.grossExposure)} />
              <Stat label="Open Positions" value={String(summary.openPositions)} />
              <Stat
                label="Diversification"
                value={`${symbols.length} assets · ${summary.strategies} strats`}
              />
            </div>
          )
        }
      </QueryState>

      <div className="grid gap-4 lg:grid-cols-5">
        <Panel title="Exposure by Asset" className="lg:col-span-3">
          {exposureBars.length ? (
            <CategoryBarChart
              data={exposureBars}
              name="Exposure"
              height={280}
              valueFormatter={(v) => compactMoney(v)}
            />
          ) : (
            <EmptyState title="No open exposure" description="Exposure appears while positions are open." />
          )}
        </Panel>

        <Panel title="Capital Allocation by Strategy" className="lg:col-span-2" flush bodyClassName="overflow-auto">
          {strategyRows.length === 0 ? (
            <div className="p-4">
              <EmptyState title="No allocation yet" description="Allocation builds from executed trades." />
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-card text-[11px] uppercase tracking-wide text-muted-foreground">
                <tr className="border-b border-border">
                  <th className="px-4 py-2 text-left font-medium">Strategy</th>
                  <th className="px-4 py-2 text-right font-medium">Trades</th>
                  <th className="px-4 py-2 text-right font-medium">Net PnL</th>
                </tr>
              </thead>
              <tbody>
                {strategyRows.map((r) => (
                  <tr key={r.key} className="border-b border-border/60">
                    <td className="px-4 py-2 truncate">{r.key}</td>
                    <td className="px-4 py-2 text-right tabular">{r.trades}</td>
                    <td className="px-4 py-2 text-right">
                      <PnlValue value={r.netPnl} market={market} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      <Panel title="Asset Analysis" flush bodyClassName="overflow-auto">
        {symbols.length === 0 ? (
          <div className="p-4">
            <EmptyState title="No assets traded" description="Per-asset analytics appear once trades arrive." />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr className="border-b border-border">
                <th className="px-4 py-2 text-left font-medium">Asset</th>
                <th className="px-4 py-2 text-right font-medium">Trades</th>
                <th className="px-4 py-2 text-right font-medium">Win %</th>
                <th className="px-4 py-2 text-right font-medium">Net PnL</th>
                <th className="px-4 py-2 text-right font-medium">Exposure</th>
                <th className="px-4 py-2 text-right font-medium">Weight</th>
              </tr>
            </thead>
            <tbody>
              {symbols.map((s) => (
                <tr key={s.key} className="border-b border-border/60">
                  <td className="px-4 py-2 font-medium tabular">{s.key}</td>
                  <td className="px-4 py-2 text-right tabular">{s.trades}</td>
                  <td className="px-4 py-2 text-right tabular">{formatPercent(s.winRate)}</td>
                  <td className="px-4 py-2 text-right">
                    <PnlValue value={s.netPnl} market={market} />
                  </td>
                  <td className="px-4 py-2 text-right tabular">{compactMoney(s.exposure)}</td>
                  <td className="px-4 py-2 text-right tabular text-muted-foreground">
                    {totalExposure ? formatPercent((s.exposure / totalExposure) * 100) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-2 text-lg font-semibold tabular">{value}</p>
    </Card>
  )
}
