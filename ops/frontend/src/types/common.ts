/** Shared primitives used across the domain models. */

/** Generic operational status used by machines, strategies and connections. */
export type Status = 'online' | 'degraded' | 'offline'

/** Direction of a price move / pnl delta. */
export type Trend = 'up' | 'down' | 'flat'

/** Severity scale shared by alerts and threshold colouring. */
export type Severity = 'info' | 'warning' | 'critical'

/** A single point on a time series chart. */
export interface TimeSeriesPoint {
  /** ISO timestamp or short label (e.g. `Jun 27`). */
  t: string
  /** Primary value. */
  v: number
}

/** A labelled value pair for categorical charts. */
export interface CategoryValue {
  label: string
  value: number
}

/** Server connection / data-feed health used by the top bar. */
export interface ConnectionState {
  status: Status
  latencyMs: number
  lastSync: string
}
