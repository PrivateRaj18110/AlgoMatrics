import type { Market, Trade } from '@/types'
import { apiGet, mockResponse, USE_MOCK } from './api/client'
import { MOCK_TRADES } from './mock/trades.mock'

function scoped(market?: Market): Trade[] {
  return market ? MOCK_TRADES.filter((t) => t.market === market) : MOCK_TRADES
}

export const tradesService = {
  /** Full blotter, optionally scoped to a single market. */
  list(market?: Market): Promise<Trade[]> {
    if (USE_MOCK) return mockResponse(scoped(market))
    return apiGet<Trade[]>(market ? `/trades?market=${market}` : '/trades')
  },
  /** Most recent N trades — used by the dashboard feed. */
  recent(limit = 12, market?: Market): Promise<Trade[]> {
    if (USE_MOCK) return mockResponse(scoped(market).slice(0, limit))
    const q = new URLSearchParams({ limit: String(limit) })
    if (market) q.set('market', market)
    return apiGet<Trade[]>(`/trades?${q.toString()}`)
  },
}
