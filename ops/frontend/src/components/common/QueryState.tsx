import type { ReactNode } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { ErrorState } from './ErrorState'

interface QueryStateProps<T> {
  query: UseQueryResult<T>
  /** Skeleton / placeholder shown while the first fetch is pending. */
  loading: ReactNode
  /** Render the resolved data. */
  children: (data: T) => ReactNode
  errorTitle?: string
}

/**
 * Standardises the loading / error / success branches for a TanStack query so
 * every page handles states identically.
 */
export function QueryState<T>({ query, loading, children, errorTitle }: QueryStateProps<T>) {
  if (query.isPending) return <>{loading}</>
  if (query.isError) {
    return <ErrorState title={errorTitle} onRetry={() => query.refetch()} />
  }
  return <>{children(query.data)}</>
}
