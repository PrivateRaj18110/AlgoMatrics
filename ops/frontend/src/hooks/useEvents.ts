import { useQuery } from '@tanstack/react-query'
import { eventsService } from '@/services'
import { useRefetchInterval } from '@/providers/settings'
import { queryKeys } from './queryKeys'

/** Loads the system event feed (newest first). */
export function useEvents(limit = 200) {
  return useQuery({
    queryKey: queryKeys.events(limit),
    queryFn: () => eventsService.list(limit),
    refetchInterval: useRefetchInterval(),
  })
}
