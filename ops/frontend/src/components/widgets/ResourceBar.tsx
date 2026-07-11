import { cn } from '@/utils/cn'
import { resourceBarColor } from '@/utils/status'

interface ResourceBarProps {
  label: string
  /** Utilisation 0–100. */
  value: number
  /** Optional unit suffix (defaults to %). */
  unit?: string
  /** Optional icon node rendered before the label. */
  icon?: React.ReactNode
  className?: string
}

/** Labelled utilisation bar (CPU / RAM / Disk) with threshold-based colouring. */
export function ResourceBar({ label, value, unit = '%', icon, className }: ResourceBarProps) {
  const clamped = Math.max(0, Math.min(100, value))
  return (
    <div className={cn('space-y-1', className)}>
      <div className="flex items-center justify-between text-xs">
        <span className="flex items-center gap-1.5 text-muted-foreground">
          {icon}
          {label}
        </span>
        <span className="tabular font-medium text-foreground">
          {value}
          {unit}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn('h-full rounded-full transition-all', resourceBarColor(clamped))}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  )
}
