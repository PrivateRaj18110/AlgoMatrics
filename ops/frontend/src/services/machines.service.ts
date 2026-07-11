import type { Machine } from '@/types'
import { apiGet, mockResponse, USE_MOCK } from './api/client'
import { MOCK_MACHINES } from './mock/machines.mock'

export const machinesService = {
  list(): Promise<Machine[]> {
    if (USE_MOCK) return mockResponse(MOCK_MACHINES)
    return apiGet<Machine[]>('/machines')
  },
  getById(id: string): Promise<Machine | undefined> {
    if (USE_MOCK) return mockResponse(MOCK_MACHINES.find((m) => m.id === id))
    return apiGet<Machine>(`/machines/${id}`)
  },
}
