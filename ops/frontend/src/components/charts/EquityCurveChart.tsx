import { memo } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TimeSeriesPoint } from '@/types'
import { formatCompactCurrency, formatCurrency, formatDateShort } from '@/utils/format'
import { AXIS_TICK, CHART_COLORS } from './chartTheme'
import { ChartTooltip } from './ChartTooltip'

interface EquityCurveChartProps {
  data: TimeSeriesPoint[]
  height?: number
  /** Tooltip value formatter (defaults to USD). Pass a market formatter for INR. */
  valueFormatter?: (value: number) => string
  /** Y-axis tick formatter (defaults to compact USD). */
  tickFormatter?: (value: number) => string
}

/** Account equity over time — the headline performance chart. */
export const EquityCurveChart = memo(function EquityCurveChart({
  data,
  height = 260,
  valueFormatter = (v) => formatCurrency(v, { precise: false }),
  tickFormatter = (v) => formatCompactCurrency(v),
}: EquityCurveChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <defs>
          <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={CHART_COLORS.primary} stopOpacity={0.4} />
            <stop offset="100%" stopColor={CHART_COLORS.primary} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="t"
          tick={AXIS_TICK}
          tickFormatter={(v: string) => formatDateShort(v)}
          tickLine={false}
          axisLine={false}
          minTickGap={32}
        />
        <YAxis
          tick={AXIS_TICK}
          tickFormatter={(v: number) => tickFormatter(v)}
          tickLine={false}
          axisLine={false}
          width={56}
          domain={['dataMin - 2000', 'dataMax + 2000']}
        />
        <Tooltip content={<ChartTooltip valueFormatter={valueFormatter} />} />
        <Area
          type="monotone"
          dataKey="v"
          name="Equity"
          stroke={CHART_COLORS.primary}
          strokeWidth={2}
          fill="url(#equityFill)"
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
})
