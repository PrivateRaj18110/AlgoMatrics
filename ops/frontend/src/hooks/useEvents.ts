import { useQuery } from '@tanstack/react-query'
import { eventsService, type EventFilters } from '@/services'
import { useRefetchInterval } from '@/providers/settings'
import { queryKeys } from './queryKeys'

/** Loads the system event feed (newest first). */
export function useEvents(limit = 200, filters: Omit<EventFilters, 'limit'> = {}) {
  return useQuery({
    queryKey: queryKeys.events(limit, filters),
    queryFn: () => eventsService.list(limit, filters),
    refetchInterval: useRefetchInterval(),
  })
}
