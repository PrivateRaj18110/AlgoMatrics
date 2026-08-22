import type { ReactNode } from 'react'
import { GripVertical } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { cn } from '@/utils/cn'

interface PanelProps {
  title?: ReactNode
  subtitle?: ReactNode
  /** Right-aligned actions / controls in the header. */
  actions?: ReactNode
  /** Remove default content padding (e.g. for tables / grids). */
  flush?: boolean
  /** Render a grab handle (class `drag-handle`) for react-grid-layout. */
  dragHandle?: boolean
  className?: string
  bodyClassName?: string
  children: ReactNode
}

/**
 * Titled card panel — the building block for every dashboard / analytics
 * section. Provides a consistent header row and optional flush body.
 */
export function Panel({
  title,
  subtitle,
  actions,
  flush,
  dragHandle,
  className,
  bodyClassName,
  children,
}: PanelProps) {
  return (
    <Card className={cn('flex h-full flex-col overflow-hidden', className)}>
      {(title || actions) && (
        <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            {dragHandle && (
              <GripVertical className="drag-handle size-4 shrink-0 cursor-grab text-muted-foreground/60 hover:text-muted-foreground active:cursor-grabbing" />
            )}
            <div className="min-w-0">
              {title && <h3 className="truncate text-sm font-semibold tracking-tight">{title}</h3>}
              {subtitle && (
                <p className="mt-0.5 truncate text-xs text-muted-foreground">{subtitle}</p>
              )}
            </div>
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={cn('min-h-0 flex-1', !flush && 'p-4', bodyClassName)}>{children}</div>
    </Card>
  )
}
