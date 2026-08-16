import type { Status } from './common'

export type RecoveryState = 'online' | 'degraded' | 'offline' | 'recovering' | 'unknown'

export interface RecoveryMachine {
  machineId: string
  machine: string
  status: Status
  recoveryState: RecoveryState
  lastHeartbeat?: string | null
  heartbeatAgeSec?: number | null
  offlineDurationSec?: number | null
  queueDepth?: number | null
  oldestPendingAgeSec?: number | null
  transportState?: string | null
  currentSessionId?: string | null
  tradingProcessState?: string | null
  lastEodSync?: string | null
  lastEodStatus?: string | null
  eodBacklog: number
  eventsRecovered: number
  acceptedEvents: number
  duplicateEvents: number
  failedEvents: number
  missingEvents: number
  gapCount: number
  lastGapAt?: string | null
  lastRecovery?: string | null
  warnings: string[]
}

export interface RecoverySummary {
  generatedAt: string
  totalMachines: number
  online: number
  degraded: number
  offline: number
  unknown: number
  recovering: number
  totalQueueDepth: number
  totalEodBacklog: number
  totalMissingEvents: number
  machines: RecoveryMachine[]
}
