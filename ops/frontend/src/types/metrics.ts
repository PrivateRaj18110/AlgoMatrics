import type { TimeSeriesPoint, Trend } from './common'

/** A single headline KPI rendered as a metric card on the dashboard. */
export interface KpiMetric {
  id: string
  label: string
  value: number
  /** How the value should be formatted by the UI. */
  format: 'currency' | 'percent' | 'number' | 'ratio'
  /** Period-over-period change in percent (optional). */
  deltaPct?: number
  trend?: Trend
  /** When set, higher is better — drives delta colouring. */
  higherIsBetter?: boolean
}

/** Aggregated dashboard payload returned by the overview service. */
export interface DashboardOverview {
  kpis: KpiMetric[]
  equityCurve: TimeSeriesPoint[]
  dailyPnl: TimeSeriesPoint[]
  /** Cumulative performance vs benchmark, percent. */
  performance: TimeSeriesPoint[]
}
