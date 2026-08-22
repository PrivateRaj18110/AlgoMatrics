import type { Broker } from '@/types'
import { apiGet, mockResponse, USE_MOCK } from './api/client'
import { MOCK_BROKERS } from './mock/brokers.mock'

export const brokersService = {
  list(): Promise<Broker[]> {
    if (USE_MOCK) return mockResponse(MOCK_BROKERS)
    return apiGet<Broker[]>('/brokers')
  },
  getById(id: string): Promise<Broker | undefined> {
    if (USE_MOCK) return mockResponse(MOCK_BROKERS.find((b) => b.id === id))
    return apiGet<Broker>(`/brokers/${id}`)
  },
}
