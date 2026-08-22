import { memo } from 'react'
import { Bar, BarChart, Cell, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TimeSeriesPoint } from '@/types'
import { formatCompactCurrency, formatCurrency, formatDateShort } from '@/utils/format'
import { AXIS_TICK, CHART_COLORS } from './chartTheme'
import { ChartTooltip } from './ChartTooltip'

interface PnlBarChartProps {
  data: TimeSeriesPoint[]
  /** `date` parses the x value as an ISO date; `label` shows it verbatim. */
  xType?: 'date' | 'label'
  height?: number
}

/** Generic green/red PnL bar chart used for daily / weekly / monthly views. */
export const PnlBarChart = memo(function PnlBarChart({
  data,
  xType = 'date',
  height = 240,
}: PnlBarChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="t"
          tick={AXIS_TICK}
          tickFormatter={xType === 'date' ? (v: string) => formatDateShort(v) : undefined}
          tickLine={false}
          axisLine={false}
          minTickGap={16}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={AXIS_TICK}
          tickFormatter={(v: number) => formatCompactCurrency(v)}
          tickLine={false}
          axisLine={false}
          width={48}
        />
        <Tooltip
          cursor={{ fill: 'rgba(148,163,184,0.08)' }}
          content={<ChartTooltip valueFormatter={(v) => formatCurrency(v, { signed: true })} />}
        />
        <Bar dataKey="v" name="PnL" radius={[2, 2, 0, 0]} isAnimationActive={false}>
          {data.map((point, i) => (
            <Cell key={i} fill={point.v >= 0 ? CHART_COLORS.success : 'var(--color-danger)'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
})
