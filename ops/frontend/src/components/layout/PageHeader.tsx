import type { ReactNode } from 'react'
import { cn } from '@/utils/cn'

interface PageHeaderProps {
  title: string
  description?: string
  /** Right-aligned actions (filters, buttons). */
  actions?: ReactNode
  className?: string
}

/** Consistent page title block used at the top of every route. */
export function PageHeader({ title, description, actions, className }: PageHeaderProps) {
  return (
    <div className={cn('flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between', className)}>
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}
