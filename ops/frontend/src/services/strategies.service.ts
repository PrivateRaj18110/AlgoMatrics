import type { Market, Strategy } from '@/types'
import { apiGet, mockResponse, USE_MOCK } from './api/client'
import { MOCK_STRATEGIES } from './mock/strategies.mock'

export const strategiesService = {
  /** List strategies, optionally scoped to a single market. */
  list(market?: Market): Promise<Strategy[]> {
    if (USE_MOCK) {
      const data = market ? MOCK_STRATEGIES.filter((s) => s.market === market) : MOCK_STRATEGIES
      return mockResponse(data)
    }
    return apiGet<Strategy[]>(market ? `/strategies?market=${market}` : '/strategies')
  },
  getById(id: string): Promise<Strategy | undefined> {
    if (USE_MOCK) return mockResponse(MOCK_STRATEGIES.find((s) => s.id === id))
    return apiGet<Strategy>(`/strategies/${id}`)
  },
}
