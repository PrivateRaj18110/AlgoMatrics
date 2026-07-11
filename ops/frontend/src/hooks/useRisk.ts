import { useQuery } from '@tanstack/react-query'
import { riskService } from '@/services'
import { useRefetchInterval } from '@/providers/settings'
import { queryKeys } from './queryKeys'

/** Loads the aggregated risk posture. */
export function useRisk() {
  return useQuery({
    queryKey: queryKeys.risk,
    queryFn: () => riskService.getOverview(),
    refetchInterval: useRefetchInterval(),
  })
}
