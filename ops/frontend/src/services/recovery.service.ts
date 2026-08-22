import type { RecoverySummary } from '@/types'
import { apiGet, mockResponse, USE_MOCK } from './api/client'

const now = new Date().toISOString()

const MOCK_RECOVERY: RecoverySummary = {
  generatedAt: now,
  totalMachines: 2,
  online: 1,
  degraded: 0,
  offline: 1,
  unknown: 0,
  recovering: 1,
  totalQueueDepth: 11,
  totalEodBacklog: 2,
  totalMissingEvents: 3,
  machines: [
    {
      machineId: 'mch-agent-gcp-trading-01',
      machine: 'gcp-trading-01',
      status: 'online',
      recoveryState: 'recovering',
      lastHeartbeat: now,
      heartbeatAgeSec: 4,
      offlineDurationSec: null,
      queueDepth: 11,
      oldestPendingAgeSec: 90,
      transportState: 'recovering',
      currentSessionId: '2026-08-10-NSE',
      tradingProcessState: 'running',
      lastEodSync: null,
      lastEodStatus: 'uploading',
      eodBacklog: 2,
      eventsRecovered: 420,
      acceptedEvents: 420,
      duplicateEvents: 12,
      failedEvents: 0,
      missingEvents: 3,
      gapCount: 1,
      lastGapAt: now,
      lastRecovery: now,
      warnings: ['sequence gaps detected', 'EOD datasets are not finalized'],
    },
    {
      machineId: 'mch-agent-london-vps',
      machine: 'london-vps',
      status: 'offline',
      recoveryState: 'offline',
      lastHeartbeat: new Date(Date.now() - 1000 * 60 * 18).toISOString(),
      heartbeatAgeSec: 1080,
      offlineDurationSec: 960,
      queueDepth: null,
      oldestPendingAgeSec: null,
      transportState: 'disconnected',
      currentSessionId: null,
      tradingProcessState: 'unknown',
      lastEodSync: null,
      lastEodStatus: null,
      eodBacklog: 0,
      eventsRecovered: 0,
      acceptedEvents: 0,
      duplicateEvents: 0,
      failedEvents: 0,
      missingEvents: 0,
      gapCount: 0,
      lastGapAt: null,
      lastRecovery: null,
      warnings: ['heartbeat is beyond offline threshold'],
    },
  ],
}

export const recoveryService = {
  summary(): Promise<RecoverySummary> {
    if (USE_MOCK) return mockResponse(MOCK_RECOVERY)
    return apiGet<RecoverySummary>('/recovery/summary')
  },
}
