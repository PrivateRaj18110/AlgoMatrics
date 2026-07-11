import { useQuery } from '@tanstack/react-query'
import { machinesService } from '@/services'
import { useRefetchInterval } from '@/providers/settings'
import { queryKeys } from './queryKeys'

/** Loads all monitored machines. */
export function useMachines() {
  return useQuery({
    queryKey: queryKeys.machines,
    queryFn: () => machinesService.list(),
    refetchInterval: useRefetchInterval(),
  })
}
