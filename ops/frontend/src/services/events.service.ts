import type { SystemEvent } from '@/types'
import { apiGet, mockResponse, USE_MOCK } from './api/client'
import { MOCK_EVENTS } from './mock/events.mock'

export interface EventFilters {
  limit?: number
  machineId?: string
  sessionId?: string
  eventType?: string
  strategy?: string
  symbol?: string
  severity?: string
  category?: string
  since?: string
  until?: string
}

function buildQuery(filters: EventFilters): string {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== '') params.set(key, String(value))
  })
  const query = params.toString()
  return query ? `?${query}` : ''
}

export const eventsService = {
  list(limit = 200, filters: Omit<EventFilters, 'limit'> = {}): Promise<SystemEvent[]> {
    if (USE_MOCK) {
      let rows = MOCK_EVENTS.slice()
      if (filters.category) rows = rows.filter((event) => event.category === filters.category)
      if (filters.severity) rows = rows.filter((event) => event.severity === filters.severity)
      return mockResponse(rows.slice(0, limit))
    }
    return apiGet<SystemEvent[]>(`/events${buildQuery({ ...filters, limit })}`)
  },
}
