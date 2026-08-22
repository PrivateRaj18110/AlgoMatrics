import { useQuery } from '@tanstack/react-query'
import { recoveryService } from '@/services'
import { useRefetchInterval } from '@/providers/settings'
import { queryKeys } from './queryKeys'

export function useRecoverySummary() {
  return useQuery({
    queryKey: queryKeys.recovery,
    queryFn: () => recoveryService.summary(),
    refetchInterval: useRefetchInterval(),
  })
}
