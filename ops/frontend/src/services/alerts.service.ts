import type { Alert } from '@/types'
import { apiGet, mockResponse, USE_MOCK } from './api/client'
import { MOCK_ALERTS } from './mock/alerts.mock'

export const alertsService = {
  list(): Promise<Alert[]> {
    if (USE_MOCK) return mockResponse(MOCK_ALERTS)
    return apiGet<Alert[]>('/alerts')
  },
}
