import type { Account } from '@/types'
import { apiGet, mockResponse, USE_MOCK } from './api/client'
import { MOCK_ACCOUNTS } from './mock/accounts.mock'

export const accountsService = {
  list(): Promise<Account[]> {
    if (USE_MOCK) return mockResponse(MOCK_ACCOUNTS)
    return apiGet<Account[]>('/accounts')
  },
  getById(id: string): Promise<Account | undefined> {
    if (USE_MOCK) return mockResponse(MOCK_ACCOUNTS.find((a) => a.id === id))
    return apiGet<Account>(`/accounts/${id}`)
  },
}
