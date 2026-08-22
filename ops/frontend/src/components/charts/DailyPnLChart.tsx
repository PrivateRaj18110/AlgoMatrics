import type { TimeSeriesPoint } from '@/types'
import { PnlBarChart } from './PnlBarChart'

interface DailyPnLChartProps {
  data: TimeSeriesPoint[]
  height?: number
}

/** Per-session realised pnl as green/red bars (thin wrapper over PnlBarChart). */
export function DailyPnLChart({ data, height = 240 }: DailyPnLChartProps) {
  return <PnlBarChart data={data} xType="date" height={height} />
}
