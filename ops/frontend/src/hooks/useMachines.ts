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

export function useMachine(machineId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.machine(machineId ?? 'unknown'),
    queryFn: () => machinesService.getById(machineId ?? ''),
    enabled: Boolean(machineId),
    refetchInterval: useRefetchInterval(),
  })
}
