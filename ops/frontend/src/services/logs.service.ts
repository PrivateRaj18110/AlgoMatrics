import type { LogEntry, LogSource } from '@/types'
import { apiGet, mockResponse, USE_MOCK } from './api/client'
import { MOCK_LOGS } from './mock/logs.mock'

export const logsService = {
  list(source?: LogSource, limit = 500): Promise<LogEntry[]> {
    if (USE_MOCK) {
      const rows = source ? MOCK_LOGS.filter((l) => l.source === source) : MOCK_LOGS
      return mockResponse(rows.slice(0, limit))
    }
    const q = new URLSearchParams({ limit: String(limit) })
    if (source) q.set('source', source)
    return apiGet<LogEntry[]>(`/logs?${q.toString()}`)
  },
}
