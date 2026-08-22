import { useQuery } from '@tanstack/react-query'
import type { LogSource } from '@/types'
import { logsService } from '@/services'
import { useRefetchInterval } from '@/providers/settings'
import { queryKeys } from './queryKeys'

/** Loads log lines, optionally filtered to a single stream. */
export function useLogs(source?: LogSource, limit = 500) {
  return useQuery({
    queryKey: queryKeys.logs(source ?? 'all', limit),
    queryFn: () => logsService.list(source, limit),
    refetchInterval: useRefetchInterval(),
  })
}
