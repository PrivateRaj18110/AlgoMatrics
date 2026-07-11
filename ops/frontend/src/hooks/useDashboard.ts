import { useQuery } from '@tanstack/react-query'
import { dashboardService } from '@/services'
import { useRefetchInterval } from '@/providers/settings'
import { queryKeys } from './queryKeys'

/** Loads the aggregated dashboard overview (KPIs + charts). */
export function useDashboard() {
  return useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: () => dashboardService.getOverview(),
    refetchInterval: useRefetchInterval(),
  })
}
