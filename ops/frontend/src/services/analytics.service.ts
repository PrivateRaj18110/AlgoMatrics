import type { AnalyticsData } from '@/types'
import { apiGet, mockResponse, USE_MOCK } from './api/client'
import { MOCK_ANALYTICS } from './mock/analytics.mock'

export const analyticsService = {
  get(): Promise<AnalyticsData> {
    if (USE_MOCK) return mockResponse(MOCK_ANALYTICS)
    return apiGet<AnalyticsData>('/analytics')
  },
}
