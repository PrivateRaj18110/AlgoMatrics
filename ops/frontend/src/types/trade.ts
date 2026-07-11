/** Trade execution domain model. */

import type { Market } from './market'

export type TradeDirection = 'long' | 'short'

export type TradeStatus = 'open' | 'closed' | 'cancelled'

export interface Trade {
  id: string
  /** Market this trade belongs to. India and International never mix. */
  market: Market
  /** ISO timestamp of entry. */
  time: string
  strategy: string
  machine: string
  broker: string
  account: string
  symbol: string
  direction: TradeDirection
  entry: number
  /** `null` while the position is still open. */
  exit: number | null
  quantity: number
  /** Realised (closed) or unrealised (open) pnl in account currency. */
  pnl: number
  /** Execution latency in milliseconds. */
  latencyMs: number
  /** Holding period in seconds. */
  durationSec: number
  status: TradeStatus
}
