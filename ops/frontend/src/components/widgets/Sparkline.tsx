import { memo } from 'react'
import { Area, AreaChart, ResponsiveContainer } from 'recharts'
import type { TimeSeriesPoint } from '@/types'

interface SparklineProps {
  data: TimeSeriesPoint[]
  /** Override the auto-derived colour (green/red from the trend). */
  color?: string
  height?: number
}

/** Minimal area sparkline — no axes/grid — for dense card layouts. */
export const Sparkline = memo(function Sparkline({ data, color, height = 40 }: SparklineProps) {
  const last = data.at(-1)?.v ?? 0
  const stroke = color ?? (last >= 0 ? 'var(--color-success)' : 'var(--color-danger)')
  const gradientId = `spark-${stroke.replace(/[^a-z]/gi, '')}`

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
            <stop offset="100%" stopColor={stroke} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="v"
          stroke={stroke}
          strokeWidth={1.5}
          fill={`url(#${gradientId})`}
          isAnimationActive={false}
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
})
