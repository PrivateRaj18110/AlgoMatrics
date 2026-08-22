import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/layout/Panel'
import { QueryState } from '@/components/common/QueryState'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { CategoryBarChart } from '@/components/charts/CategoryBarChart'
import { CHART_COLORS } from '@/components/charts/chartTheme'
import { useRisk } from '@/hooks/useRisk'
import { cn } from '@/utils/cn'
import { formatCompactCurrency, formatCurrency, formatPercent } from '@/utils/format'
import type { RiskData, RiskLimit } from '@/types'

export default function RiskPage() {
  const query = useRisk()

  return (
    <div className="space-y-5">
      <PageHeader
        title="Risk"
        description="Loss limits, exposure and drawdown across the entire book."
      />

      <QueryState query={query} loading={<RiskSkeleton />}>
        {(data) => <RiskContent data={data} />}
      </QueryState>
    </div>
  )
}

function RiskContent({ data }: { data: RiskData }) {
  const exposurePct = Math.min(100, Math.round((data.currentExposure / data.maxExposure) * 100))

  return (
    <div className="space-y-5">
      {/* Loss limit gauges */}
      <div className="grid gap-4 lg:grid-cols-3">
        <LimitGauge limit={data.dailyLoss} />
        <LimitGauge limit={data.weeklyLoss} />
        <LimitGauge limit={data.monthlyLoss} />
      </div>

      {/* Posture KPIs */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
        <Kpi label="Current Exposure" value={formatCompactCurrency(data.currentExposure)} sub={`${exposurePct}% of cap`} />
        <Kpi label="Max Exposure" value={formatCompactCurrency(data.maxExposure)} />
        <Kpi label="Current Margin" value={formatCompactCurrency(data.currentMargin)} />
        <Kpi label="Margin Level" value={`${data.marginLevelPct}%`} />
        <Kpi label="Current Drawdown" value={formatPercent(data.currentDrawdownPct)} tone="text-danger" />
        <Kpi label="Max Drawdown" value={formatPercent(data.maxDrawdownPct)} tone="text-danger" />
      </div>

      {/* Exposure cap bar */}
      <Panel title="Exposure Utilisation" subtitle="Deployed notional vs configured cap">
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              {formatCurrency(data.currentExposure)} / {formatCurrency(data.maxExposure)}
            </span>
            <span className="tabular font-semibold">{exposurePct}%</span>
          </div>
          <div className="h-3 w-full overflow-hidden rounded-full bg-muted">
            <div
              className={cn(
                'h-full rounded-full transition-all',
                exposurePct >= 90 ? 'bg-danger' : exposurePct >= 70 ? 'bg-warning' : 'bg-success',
              )}
              style={{ width: `${exposurePct}%` }}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            1-day 95% Value at Risk: <span className="tabular font-medium text-foreground">{formatCurrency(data.valueAtRisk)}</span>
          </p>
        </div>
      </Panel>

      {/* Exposure breakdowns */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Exposure by Symbol" bodyClassName="p-3">
          <CategoryBarChart
            data={data.exposureBySymbol}
            name="Exposure"
            color={CHART_COLORS.primary}
            valueFormatter={(v) => formatCompactCurrency(v)}
          />
        </Panel>
        <Panel title="Exposure by Strategy" bodyClassName="p-3">
          <CategoryBarChart
            data={data.exposureByStrategy}
            name="Exposure"
            color={CHART_COLORS.purple}
            valueFormatter={(v) => formatCompactCurrency(v)}
          />
        </Panel>
        <Panel title="Exposure by Broker" bodyClassName="p-3">
          <CategoryBarChart
            data={data.exposureByBroker}
            name="Exposure"
            color={CHART_COLORS.cyan}
            valueFormatter={(v) => formatCompactCurrency(v)}
          />
        </Panel>
      </div>
    </div>
  )
}

/** Used-vs-limit gauge with threshold colouring. */
function LimitGauge({ limit }: { limit: RiskLimit }) {
  const pct = Math.min(100, Math.round((limit.used / limit.limit) * 100))
  const fmt = (v: number) => (limit.unit === 'currency' ? formatCurrency(v) : formatPercent(v))
  const color = pct >= 90 ? 'bg-danger' : pct >= 70 ? 'bg-warning' : 'bg-success'
  return (
    <Card className="space-y-3 p-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">{limit.label}</p>
        <span className={cn('text-xs font-semibold tabular', pct >= 90 ? 'text-danger' : pct >= 70 ? 'text-warning' : 'text-success')}>
          {pct}%
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div className={cn('h-full rounded-full transition-all', color)} style={{ width: `${pct}%` }} />
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span className="tabular">Used {fmt(limit.used)}</span>
        <span className="tabular">Limit {fmt(limit.limit)}</span>
      </div>
    </Card>
  )
}

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn('mt-2 text-xl font-semibold tabular', tone ?? 'text-foreground')}>{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-muted-foreground">{sub}</p>}
    </Card>
  )
}

function RiskSkeleton() {
  return (
    <div className="space-y-5">
      <div className="grid gap-4 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-72" />
        ))}
      </div>
    </div>
  )
}
