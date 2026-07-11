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
import { formatPercent } from '@/utils/format'
import { bySymbol } from './marketDerivations'

export default function MarketRiskPage() {
  const { market, meta, compactMoney } = useMarket()
  const query = useTrades(market)

  const risk = useMemo(() => {
    const open = (query.data ?? []).filter((t) => t.status === 'open')
    const symbols = query.data ? bySymbol(query.data) : []
    const grossExposure = open.reduce((s, t) => s + Math.abs(t.entry * t.quantity), 0)
    const netExposure = open.reduce(
      (s, t) => s + (t.direction === 'long' ? 1 : -1) * Math.abs(t.entry * t.quantity),
      0,
    )
    const largest = symbols.reduce((m, s) => Math.max(m, s.exposure), 0)
    const concentration = grossExposure ? (largest / grossExposure) * 100 : 0
    const exposureBars = symbols
      .filter((s) => s.exposure > 0)
      .map((s) => ({ label: s.key, value: Math.round(s.exposure) }))
    return { open: open.length, grossExposure, netExposure, concentration, exposureBars }
  }, [query.data])

  return (
    <div className="space-y-5">
      <PageHeader
        title={`${meta.label} · Risk`}
        description="Live exposure, concentration and directional bias for this market."
      />

      <QueryState
        query={query}
        loading={
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        }
      >
        {() => (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat label="Gross Exposure" value={compactMoney(risk.grossExposure)} />
              <Stat
                label="Net Exposure"
                value={`${risk.netExposure >= 0 ? 'Long ' : 'Short '}${compactMoney(Math.abs(risk.netExposure))}`}
              />
              <Stat label="Open Positions" value={String(risk.open)} />
              <Stat label="Concentration" value={formatPercent(risk.concentration)} />
            </div>

            <Panel title="Risk Contribution by Asset">
              {risk.exposureBars.length ? (
                <CategoryBarChart
                  data={risk.exposureBars}
                  name="Exposure"
                  height={300}
                  valueFormatter={(v) => compactMoney(v)}
                />
              ) : (
                <EmptyState title="No open risk" description="Exposure appears while positions are open." />
              )}
            </Panel>
          </>
        )}
      </QueryState>
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
