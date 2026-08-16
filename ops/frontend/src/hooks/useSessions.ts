import { useQuery } from '@tanstack/react-query'
import { sessionsService } from '@/services'
import { useRefetchInterval } from '@/providers/settings'
import { queryKeys } from './queryKeys'

export function useSessions(machineId?: string) {
  return useQuery({
    queryKey: queryKeys.sessions(machineId),
    queryFn: () => sessionsService.list(machineId),
    refetchInterval: useRefetchInterval(),
  })
}

export function useSessionDetail(sessionId: string | undefined, machineId?: string) {
  return useQuery({
    queryKey: queryKeys.session(sessionId ?? 'unknown', machineId),
    queryFn: () => sessionsService.get(sessionId ?? '', machineId),
    enabled: Boolean(sessionId),
    refetchInterval: useRefetchInterval(),
  })
}
