import { useQuery } from '@tanstack/react-query'
import { analyticsService } from '@/services'
import { queryKeys } from './queryKeys'

/** Loads the analytics dataset (series + heatmaps). */
export function useAnalytics() {
  return useQuery({
    queryKey: queryKeys.analytics,
    queryFn: () => analyticsService.get(),
  })
}
