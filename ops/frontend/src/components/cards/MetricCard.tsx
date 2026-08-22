import { memo } from 'react'
import { Card } from '@/components/ui/card'
import { DeltaBadge } from '@/components/common/DeltaBadge'
import type { KpiMetric, Market } from '@/types'
import { cn } from '@/utils/cn'
import { formatCurrency, formatMoney, formatNumber, formatPercent } from '@/utils/format'

function formatValue(metric: KpiMetric, market?: Market): string {
  switch (metric.format) {
    case 'currency':
      return market
        ? formatMoney(metric.value, market, { signed: metric.value !== 0 })
        : formatCurrency(metric.value, { signed: metric.value !== 0 })
    case 'percent':
      return formatPercent(metric.value, 1)
    case 'ratio':
      return metric.value.toFixed(2)
    case 'number':
    default:
      return formatNumber(metric.value)
  }
}

/** Colour the headline value for money / drawdown metrics. */
function valueColor(metric: KpiMetric): string {
  if (metric.format === 'currency') {
    if (metric.value > 0) return 'text-success'
    if (metric.value < 0) return 'text-danger'
  }
  if (metric.id === 'current_dd' || metric.id === 'max_dd') {
    return metric.value < 0 ? 'text-danger' : 'text-foreground'
  }
  return 'text-foreground'
}

/** Headline KPI tile for the dashboard grid. */
export const MetricCard = memo(function MetricCard({
  metric,
  market,
}: {
  metric: KpiMetric
  /** When set, currency metrics render in this market's currency. */
  market?: Market
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {metric.label}
        </p>
        {metric.deltaPct != null && (
          <DeltaBadge value={metric.deltaPct} higherIsBetter={metric.higherIsBetter ?? true} />
        )}
      </div>
      <p className={cn('mt-2 text-2xl font-semibold tabular tracking-tight', valueColor(metric))}>
        {formatValue(metric, market)}
      </p>
    </Card>
  )
})
