import type { ExecutionData } from '@/types'
import { apiGet, mockResponse, USE_MOCK } from './api/client'
import { MOCK_EXECUTION } from './mock/execution.mock'

export const executionService = {
  getOverview(): Promise<ExecutionData> {
    if (USE_MOCK) return mockResponse(MOCK_EXECUTION)
    return apiGet<ExecutionData>('/execution/overview')
  },
}
