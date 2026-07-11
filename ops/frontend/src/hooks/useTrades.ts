import { useQuery } from '@tanstack/react-query'
import { tradesService } from '@/services'
import { useRefetchInterval } from '@/providers/settings'
import type { Market } from '@/types'
import { queryKeys } from './queryKeys'

/** Loads the full trade blotter, optionally scoped to a single market. */
export function useTrades(market?: Market) {
  return useQuery({
    queryKey: market ? queryKeys.tradesByMarket(market) : queryKeys.trades,
    queryFn: () => tradesService.list(market),
    refetchInterval: useRefetchInterval(),
  })
}

/** Loads the most recent N trades for a feed, optionally scoped to a market. */
export function useRecentTrades(limit = 12, market?: Market) {
  return useQuery({
    queryKey: market ? queryKeys.recentTradesByMarket(limit, market) : queryKeys.recentTrades(limit),
    queryFn: () => tradesService.recent(limit, market),
    refetchInterval: useRefetchInterval(),
  })
}
