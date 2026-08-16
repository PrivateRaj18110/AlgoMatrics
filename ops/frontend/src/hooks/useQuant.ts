import { useMutation, useQuery } from '@tanstack/react-query'
import { quantService } from '@/services'
import type { QuantAnalyticsCategory, SyntheticReplayRequest } from '@/types'
import { useRefetchInterval } from '@/providers/settings'
import { queryKeys } from './queryKeys'

export function useQuantReports() {
  return useQuery({
    queryKey: queryKeys.quantReports,
    queryFn: () => quantService.listReports(),
    refetchInterval: useRefetchInterval(),
  })
}

export function useQuantAnalytics(category: QuantAnalyticsCategory, datasetId?: string) {
  return useQuery({
    queryKey: queryKeys.quantAnalytics(category, datasetId),
    queryFn: () => quantService.getAnalytics(category, datasetId),
    refetchInterval: useRefetchInterval(),
  })
}

export function useSyntheticReplay() {
  return useMutation({
    mutationFn: (payload: SyntheticReplayRequest) => quantService.syntheticReplay(payload),
  })
}
