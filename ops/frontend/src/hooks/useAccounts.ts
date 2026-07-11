import { useQuery } from '@tanstack/react-query'
import { accountsService } from '@/services'
import { useRefetchInterval } from '@/providers/settings'
import { queryKeys } from './queryKeys'

/** Loads all trading accounts. */
export function useAccounts() {
  return useQuery({
    queryKey: queryKeys.accounts,
    queryFn: () => accountsService.list(),
    refetchInterval: useRefetchInterval(),
  })
}
