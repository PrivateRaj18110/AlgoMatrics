import type { Severity } from './common'

/** Domain a live event originates from — drives the terminal colour coding. */
export type EventCategory =
  | 'trade'
  | 'strategy'
  | 'machine'
  | 'broker'
  | 'system'
  | 'database'
  | 'risk'
  | 'data'

/** A single line in the Bloomberg-style live event terminal. */
export interface SystemEvent {
  id: string
  /** ISO timestamp. */
  time: string
  category: EventCategory
  severity: Severity
  /** Originating machine / strategy / broker label. */
  source: string
  message: string
  machineId?: string | null
  eventType?: string | null
  strategy?: string | null
  symbol?: string | null
  sessionId?: string | null
  sequenceId?: number | null
  payloadSummary?: string | null
}
