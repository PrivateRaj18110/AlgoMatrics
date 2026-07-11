import type { SystemEvent } from '@/types'
import { apiGet, mockResponse, USE_MOCK } from './api/client'
import { MOCK_EVENTS } from './mock/events.mock'

export const eventsService = {
  list(limit = 200): Promise<SystemEvent[]> {
    if (USE_MOCK) return mockResponse(MOCK_EVENTS.slice(0, limit))
    return apiGet<SystemEvent[]>(`/events?limit=${limit}`)
  },
}
