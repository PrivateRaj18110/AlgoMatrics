import type { DashboardOverview } from '@/types'
import { apiGet, mockResponse, USE_MOCK } from './api/client'
import { MOCK_DASHBOARD } from './mock/dashboard.mock'

/** Aggregated KPI + chart payload for the main dashboard. */
export const dashboardService = {
  getOverview(): Promise<DashboardOverview> {
    if (USE_MOCK) return mockResponse(MOCK_DASHBOARD)
    return apiGet<DashboardOverview>('/dashboard/overview')
  },
}
