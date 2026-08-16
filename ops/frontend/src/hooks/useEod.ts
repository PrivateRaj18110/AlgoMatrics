import { useQuery } from '@tanstack/react-query'
import { eodService, type EodDatasetFilters } from '@/services'
import { useRefetchInterval } from '@/providers/settings'
import { queryKeys } from './queryKeys'

export function useEodDatasets(filters: EodDatasetFilters = {}) {
  return useQuery({
    queryKey: queryKeys.eodDatasets({ ...filters }),
    queryFn: () => eodService.list(filters),
    refetchInterval: useRefetchInterval(),
  })
}

export function useEodReconciliation() {
  return useQuery({
    queryKey: queryKeys.eodReconciliation,
    queryFn: () => eodService.reconciliation(),
    refetchInterval: useRefetchInterval(),
  })
}
