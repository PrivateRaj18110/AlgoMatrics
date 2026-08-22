import type { Status } from './common'

/** A monitored host (VPS, cloud instance or local workstation). */
export interface Machine {
  id: string
  name: string
  /** Geographic / provider label, e.g. `London · Equinix LD4`. */
  location: string
  provider: string
  status: Status
  /** Percentages (0–100). */
  cpu: number
  ram: number
  disk: number
  /** CPU temperature in °C (null when the host does not report it). */
  temperatureC: number | null
  /** Round-trip to the data feed in ms. */
  internetMs: number
  /** Round-trip to the broker gateway in ms. */
  brokerPingMs: number
  /** Whether the Python trading runtime is alive. */
  pythonStatus: Status
  /** Uptime in seconds. */
  uptimeSec: number
  /** ISO timestamp of the last heartbeat. */
  lastHeartbeat: string
  /** Number of strategies hosted on this machine. */
  strategyCount: number
  agentId?: string | null
  agentVersion?: string | null
  hostname?: string | null
  environment?: string | null
  lastEvent?: string | null
  lastTrade?: string | null
  lastError?: string | null
  lastSuccessfulUpload?: string | null
  queueDepth?: number | null
  oldestPendingAgeSec?: number | null
  transportState?: string | null
  currentSessionId?: string | null
  tradingProcessState?: string | null
  lastEodSync?: string | null
  lastEodStatus?: string | null
  recoveryState?: string | null
  lastRecovery?: string | null
  eventsRecovered?: number | null
  eodBacklog?: number | null
}
