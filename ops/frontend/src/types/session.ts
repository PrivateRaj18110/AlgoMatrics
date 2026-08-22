import type { EodDataset } from './eod'
import type { SystemEvent } from './event'

export interface TradingSession {
  sessionId: string
  machineId: string
  machine: string
  status: 'open' | 'closed'
  startedAt?: string | null
  endedAt?: string | null
  lastEventAt?: string | null
  eventCount: number
  tradeCount: number
}

export interface SessionDetail {
  session: TradingSession
  recentEvents: SystemEvent[]
  eodDatasets: EodDataset[]
}
