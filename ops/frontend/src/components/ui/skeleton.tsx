import type { HTMLAttributes } from 'react'
import { cn } from '@/utils/cn'

/** Loading placeholder block with a subtle pulse. */
function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('animate-pulse rounded-md bg-muted', className)} {...props} />
}

export { Skeleton }
