import { useQuery } from '@tanstack/react-query'
import { executionService } from '@/services'
import { useRefetchInterval } from '@/providers/settings'
import { queryKeys } from './queryKeys'

/** Loads the execution pipeline + latency overview. */
export function useExecution() {
  return useQuery({
    queryKey: queryKeys.execution,
    queryFn: () => executionService.getOverview(),
    refetchInterval: useRefetchInterval(),
  })
}
