import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/layout/Panel'
import { Badge } from '@/components/ui/badge'
import { QueryState } from '@/components/common/QueryState'
import { useStrategies } from '@/hooks/useStrategies'
import { MARKETS, type Status, type Strategy } from '@/types'
import { formatPercent } from '@/utils/format'
import { marketPath } from '@/components/navigation/navConfig'

/** Map live telemetry onto a research lifecycle stage (real model registry lands later). */
function researchStage(status: Status): { label: string; variant: 'success' | 'warning' | 'muted' } {
  switch (status) {
    case 'online':
      return { label: 'Production', variant: 'success' }
    case 'degraded':
      return { label: 'Paper Trading', variant: 'warning' }
    default:
      return { label: 'Backtest', variant: 'muted' }
  }
}

/** Confidence proxy from profit factor until a research score is wired up. */
function confidence(s: Strategy): number {
  return Math.max(0, Math.min(100, Math.round((s.profitFactor / 2.6) * 100)))
}

export default function ResearchPage() {
  const query = useStrategies()
  const grouped = useMemo(() => {
    const data = query.data ?? []
    return (Object.keys(MARKETS) as (keyof typeof MARKETS)[]).map((market) => ({
      market,
      meta: MARKETS[market],
      rows: data.filter((s) => s.market === market),
    }))
  }, [query.data])

  return (
    <div className="space-y-5">
      <PageHeader
        title="Research"
        description="Strategy lifecycle, confidence and deployment status across every market."
      />

      <QueryState query={query} loading={<div className="h-64 animate-pulse rounded-lg bg-muted" />}>
        {() => (
          <div className="space-y-5">
            {grouped.map(({ market, meta, rows }) => (
              <Panel
                key={market}
                title={`${meta.label} · ${rows.length} strategies`}
                flush
                bodyClassName="overflow-auto"
              >
                <table className="w-full text-sm">
                  <thead className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    <tr className="border-b border-border">
                      <th className="px-4 py-2 text-left font-medium">Strategy</th>
                      <th className="px-4 py-2 text-left font-medium">Stage</th>
                      <th className="px-4 py-2 text-right font-medium">Win %</th>
                      <th className="px-4 py-2 text-right font-medium">Profit Factor</th>
                      <th className="px-4 py-2 text-right font-medium">Confidence</th>
                      <th className="px-4 py-2 text-right font-medium" />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((s) => {
                      const stage = researchStage(s.status)
                      return (
                        <tr key={s.id} className="border-b border-border/60">
                          <td className="px-4 py-2">
                            <div className="flex items-center gap-2">
                              <span className="font-medium">{s.name}</span>
                              <Badge variant="outline" className="tabular">
                                {s.code}
                              </Badge>
                            </div>
                          </td>
                          <td className="px-4 py-2">
                            <Badge variant={stage.variant}>{stage.label}</Badge>
                          </td>
                          <td className="px-4 py-2 text-right tabular">{formatPercent(s.winRate)}</td>
                          <td className="px-4 py-2 text-right tabular">{s.profitFactor.toFixed(2)}</td>
                          <td className="px-4 py-2 text-right tabular">{confidence(s)}%</td>
                          <td className="px-4 py-2 text-right">
                            <Link
                              to={marketPath(market, 'strategies')}
                              className="text-xs text-primary hover:underline"
                            >
                              Open
                            </Link>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </Panel>
            ))}
          </div>
        )}
      </QueryState>
    </div>
  )
}
