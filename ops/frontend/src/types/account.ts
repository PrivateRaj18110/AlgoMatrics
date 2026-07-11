import type { Status, TimeSeriesPoint } from './common'

export type AccountType = 'live' | 'demo' | 'prop'

/** A trading account held at a broker. */
export interface Account {
  id: string
  label: string
  broker: string
  type: AccountType
  currency: string
  status: Status
  balance: number
  equity: number
  /** Realised pnl booked today. */
  todayPnl: number
  /** Unrealised pnl on open positions. */
  openPnl: number
  /** Margin level (equity / margin) as a percentage. */
  marginLevelPct: number
  leverage: number
  openPositions: number
  /** Strategy codes deployed against this account. */
  strategies: string[]
  /** Equity history for the account sparkline. */
  equityCurve: TimeSeriesPoint[]
}
