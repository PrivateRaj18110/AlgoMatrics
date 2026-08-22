import type { RiskData } from '@/types'
import { apiGet, mockResponse, USE_MOCK } from './api/client'
import { MOCK_RISK } from './mock/risk.mock'

export const riskService = {
  getOverview(): Promise<RiskData> {
    if (USE_MOCK) return mockResponse(MOCK_RISK)
    return apiGet<RiskData>('/risk/overview')
  },
}
