import { memo } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TimeSeriesPoint } from '@/types'
import { formatDateShort, formatPercent } from '@/utils/format'
import { AXIS_TICK, CHART_COLORS } from './chartTheme'
import { ChartTooltip } from './ChartTooltip'

interface PerformanceChartProps {
  data: TimeSeriesPoint[]
  height?: number
}

/** Cumulative performance (%) line chart. */
export const PerformanceChart = memo(function PerformanceChart({
  data,
  height = 240,
}: PerformanceChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
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
          tickFormatter={(v: number) => `${v}%`}
          tickLine={false}
          axisLine={false}
          width={44}
        />
        <Tooltip content={<ChartTooltip valueFormatter={(v) => formatPercent(v, 2)} />} />
        <Line
          type="monotone"
          dataKey="v"
          name="Performance"
          stroke={CHART_COLORS.cyan}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
})
