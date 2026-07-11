import type { Status, TimeSeriesPoint } from './common'
import type { Market } from './market'

/** A trading strategy / algo instance running on a machine. */
export interface Strategy {
  id: string
  /** Market this strategy belongs to. India and International never mix. */
  market: Market
  name: string
  /** Short tag, e.g. `MR`, `MOM`, `ARB`. */
  code: string
  description: string
  status: Status
  /** Machine id the strategy is deployed on. */
  machineId: string
  machineName: string
  broker: string
  symbols: string[]
  todayPnl: number
  weekPnl: number
  /** Trades executed today. */
  todayTrades: number
  openPositions: number
  winRate: number
  profitFactor: number
  /** Average execution latency in ms. */
  avgLatencyMs: number
  /** Sparkline of recent intraday pnl. */
  sparkline: TimeSeriesPoint[]
  /** ISO timestamp of the last received heartbeat. */
  lastHeartbeat: string
}
