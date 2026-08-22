import { memo } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { CategoryValue } from '@/types'
import { AXIS_TICK, CHART_COLORS } from './chartTheme'
import { ChartTooltip } from './ChartTooltip'

interface CategoryBarChartProps {
  data: CategoryValue[]
  name: string
  color?: string
  height?: number
  /** Format axis ticks + tooltip values. */
  valueFormatter?: (value: number) => string
}

/** Reusable categorical bar chart (win rate, profit factor, latency, …). */
export const CategoryBarChart = memo(function CategoryBarChart({
  data,
  name,
  color = CHART_COLORS.primary,
  height = 240,
  valueFormatter,
}: CategoryBarChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="label" tick={AXIS_TICK} tickLine={false} axisLine={false} interval={0} />
        <YAxis
          tick={AXIS_TICK}
          tickFormatter={valueFormatter}
          tickLine={false}
          axisLine={false}
          width={44}
        />
        <Tooltip
          cursor={{ fill: 'rgba(148,163,184,0.08)' }}
          content={<ChartTooltip valueFormatter={(v) => (valueFormatter ? valueFormatter(v) : String(v))} />}
        />
        <Bar dataKey="value" name={name} fill={color} radius={[3, 3, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  )
})
