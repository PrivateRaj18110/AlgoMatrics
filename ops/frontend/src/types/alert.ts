import type { Severity } from './common'

/** Categories surfaced by the alert center. */
export type AlertType =
  | 'machine_offline'
  | 'high_cpu'
  | 'high_ram'
  | 'high_latency'
  | 'broker_offline'
  | 'strategy_crash'

export interface Alert {
  id: string
  type: AlertType
  severity: Severity
  title: string
  message: string
  /** Originating machine / strategy label. */
  source: string
  /** ISO timestamp. */
  time: string
  acknowledged: boolean
}
