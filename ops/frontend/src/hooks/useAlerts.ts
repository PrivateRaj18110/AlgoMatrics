import { useQuery } from '@tanstack/react-query'
import { alertsService } from '@/services'
import { useRefetchInterval } from '@/providers/settings'
import { queryKeys } from './queryKeys'

/** Loads the alert center feed. */
export function useAlerts() {
  return useQuery({
    queryKey: queryKeys.alerts,
    queryFn: () => alertsService.list(),
    refetchInterval: useRefetchInterval(),
  })
}
