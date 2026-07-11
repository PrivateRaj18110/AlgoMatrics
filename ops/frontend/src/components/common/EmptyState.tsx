import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Inbox } from 'lucide-react'
import { cn } from '@/utils/cn'

interface EmptyStateProps {
  icon?: LucideIcon
  title: string
  description?: string
  className?: string
  action?: ReactNode
}

/** Neutral placeholder for empty lists / panels. */
export function EmptyState({ icon: Icon = Inbox, title, description, className, action }: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-2 px-6 py-10 text-center',
        className,
      )}
    >
      <div className="rounded-full bg-muted p-3 text-muted-foreground">
        <Icon className="size-5" />
      </div>
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="max-w-xs text-xs text-muted-foreground">{description}</p>}
      {action}
    </div>
  )
}
