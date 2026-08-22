import { useQuery } from '@tanstack/react-query'
import { brokersService } from '@/services'
import { useRefetchInterval } from '@/providers/settings'
import { queryKeys } from './queryKeys'

/** Loads all connected brokers. */
export function useBrokers() {
  return useQuery({
    queryKey: queryKeys.brokers,
    queryFn: () => brokersService.list(),
    refetchInterval: useRefetchInterval(),
  })
}
