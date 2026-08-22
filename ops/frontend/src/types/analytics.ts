import type { CategoryValue, TimeSeriesPoint } from './common'

/** One cell of a calendar / day-of-week × hour heatmap. */
export interface HeatmapCell {
  /** Row label (e.g. weekday). */
  row: string
  /** Column label (e.g. hour bucket). */
  col: string
  value: number
}

export interface HeatmapSeries {
  rows: string[]
  cols: string[]
  cells: HeatmapCell[]
}

/** Full analytics payload. */
export interface AnalyticsData {
  dailyPnl: TimeSeriesPoint[]
  weeklyPnl: TimeSeriesPoint[]
  monthlyPnl: TimeSeriesPoint[]
  /** Win rate by strategy. */
  winRateByStrategy: CategoryValue[]
  /** Profit factor by strategy. */
  profitFactorByStrategy: CategoryValue[]
  /** Average latency by machine. */
  latencyByMachine: CategoryValue[]
  /** PnL heatmap (weekday × hour). */
  pnlHeatmap: HeatmapSeries
  /** Machine load heatmap (machine × hour, CPU %). */
  machineLoadHeatmap: HeatmapSeries
}
