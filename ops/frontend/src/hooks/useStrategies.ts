import { useQuery } from '@tanstack/react-query'
import { strategiesService } from '@/services'
import { useRefetchInterval } from '@/providers/settings'
import type { Market } from '@/types'
import { queryKeys } from './queryKeys'

/** Loads strategies, optionally scoped to a single market. */
export function useStrategies(market?: Market) {
  return useQuery({
    queryKey: market ? queryKeys.strategiesByMarket(market) : queryKeys.strategies,
    queryFn: () => strategiesService.list(market),
    refetchInterval: useRefetchInterval(),
  })
}
