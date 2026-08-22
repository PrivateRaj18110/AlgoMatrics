import type { Status, TimeSeriesPoint } from './common'

/** A connected broker / liquidity venue. Scales to an unlimited roster. */
export interface Broker {
  id: string
  name: string
  /** Trade server / gateway, e.g. `ICMarkets-Live12`. */
  server: string
  connection: Status
  /** Linked account label. */
  account: string
  /** Average spread in pips on the primary symbol. */
  spreadPips: number
  balance: number
  equity: number
  margin: number
  freeMargin: number
  /** Margin level (equity / margin) as a percentage. */
  marginLevelPct: number
  /** Leverage as the `x` in `1:x`. */
  leverage: number
  openPositions: number
  pendingOrders: number
  rejectedOrders: number
  /** Gateway round-trip in ms. */
  pingMs: number
  /** ISO timestamp of the last quote / heartbeat. */
  lastSync: string
  /** Recent ping history for the card sparkline. */
  pingHistory: TimeSeriesPoint[]
}
