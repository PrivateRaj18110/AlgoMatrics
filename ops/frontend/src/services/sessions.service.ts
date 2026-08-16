import type { SessionDetail, TradingSession } from '@/types'
import { apiGet, mockResponse, USE_MOCK } from './api/client'
import { MOCK_EVENTS } from './mock/events.mock'
import { MOCK_MACHINES } from './mock/machines.mock'

const MOCK_SESSIONS: TradingSession[] = MOCK_MACHINES.slice(0, 2).map((machine, index) => ({
  sessionId: `mock-session-${index + 1}`,
  machineId: machine.id,
  machine: machine.name,
  status: 'open',
  startedAt: new Date(Date.now() - 1000 * 60 * 60 * (index + 1)).toISOString(),
  endedAt: null,
  lastEventAt: machine.lastEvent ?? machine.lastHeartbeat,
  eventCount: 24 - index * 5,
  tradeCount: 8 - index * 2,
}))

function mockDetail(sessionId: string): SessionDetail {
  const session = MOCK_SESSIONS.find((row) => row.sessionId === sessionId) ?? MOCK_SESSIONS[0]
  return {
    session,
    recentEvents: MOCK_EVENTS.filter((event) => event.machineId === session.machineId).slice(0, 20),
    eodDatasets: [],
  }
}

export const sessionsService = {
  list(machineId?: string): Promise<TradingSession[]> {
    if (USE_MOCK) {
      const rows = machineId
        ? MOCK_SESSIONS.filter((session) => session.machineId === machineId)
        : MOCK_SESSIONS
      return mockResponse(rows)
    }
    const params = machineId ? `?machineId=${encodeURIComponent(machineId)}` : ''
    return apiGet<TradingSession[]>(`/sessions${params}`)
  },
  get(sessionId: string, machineId?: string): Promise<SessionDetail> {
    if (USE_MOCK) return mockResponse(mockDetail(sessionId))
    const params = machineId ? `?machineId=${encodeURIComponent(machineId)}` : ''
    return apiGet<SessionDetail>(`/sessions/${encodeURIComponent(sessionId)}${params}`)
  },
}
