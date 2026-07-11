import type { AnalyticsData, CategoryValue, HeatmapCell, HeatmapSeries, TimeSeriesPoint } from '@/types'
import { MOCK_MACHINES } from './machines.mock'
import { MOCK_STRATEGIES } from './strategies.mock'
import { createRng, randFloat, round } from './seed'

const rng = createRng(0xa1a1)
const now = Date.now()
const dayMs = 86_400_000

const dailyPnl: TimeSeriesPoint[] = Array.from({ length: 30 }, (_, i) => {
  const d = new Date(now - (29 - i) * dayMs)
  return { t: d.toISOString().slice(0, 10), v: round(randFloat(rng, -2800, 4800), 0) }
})

const weeklyPnl: TimeSeriesPoint[] = Array.from({ length: 12 }, (_, i) => ({
  t: `W${i + 1}`,
  v: round(randFloat(rng, -6000, 15_000), 0),
}))

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const monthlyPnl: TimeSeriesPoint[] = MONTHS.slice(0, 6).map((m) => ({
  t: m,
  v: round(randFloat(rng, -8000, 42_000), 0),
}))

const winRateByStrategy: CategoryValue[] = MOCK_STRATEGIES.map((s) => ({
  label: s.code,
  value: s.winRate,
}))

const profitFactorByStrategy: CategoryValue[] = MOCK_STRATEGIES.map((s) => ({
  label: s.code,
  value: s.profitFactor,
}))

const latencyByMachine: CategoryValue[] = MOCK_MACHINES.map((m) => ({
  label: m.name,
  value: m.brokerPingMs || round(randFloat(rng, 20, 120), 0),
}))

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
const HOURS = ['08', '10', '12', '14', '16', '18', '20']

function buildHeatmap(rows: string[], cols: string[], min: number, max: number): HeatmapSeries {
  const cells: HeatmapCell[] = []
  for (const row of rows) {
    for (const col of cols) {
      cells.push({ row, col, value: round(randFloat(rng, min, max), 0) })
    }
  }
  return { rows, cols, cells }
}

const pnlHeatmap = buildHeatmap(WEEKDAYS, HOURS, -1200, 2400)
const machineLoadHeatmap = buildHeatmap(
  MOCK_MACHINES.map((m) => m.name),
  HOURS,
  10,
  98,
)

export const MOCK_ANALYTICS: AnalyticsData = {
  dailyPnl,
  weeklyPnl,
  monthlyPnl,
  winRateByStrategy,
  profitFactorByStrategy,
  latencyByMachine,
  pnlHeatmap,
  machineLoadHeatmap,
}
