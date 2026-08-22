import { cn } from '@/utils/cn'

type Formatter = (value: number, name: string) => string

/** Subset of the props Recharts injects into a custom tooltip `content`. */
interface TooltipPayloadItem {
  value?: number | string
  name?: string | number
  color?: string
  dataKey?: string | number
}

interface ChartTooltipProps {
  active?: boolean
  payload?: TooltipPayloadItem[]
  label?: string | number
  /** Format each value (defaults to a localized number). */
  valueFormatter?: Formatter
  className?: string
}

/**
 * Themed Recharts tooltip — dark popover surface with mono values. Props are
 * declared loosely so the component is decoupled from Recharts' internal
 * tooltip typings across versions.
 */
export function ChartTooltip({ active, payload, label, valueFormatter, className }: ChartTooltipProps) {
  if (!active || !payload?.length) return null

  return (
    <div
      className={cn(
        'rounded-lg border border-border bg-popover/95 px-3 py-2 text-xs shadow-lg backdrop-blur',
        className,
      )}
    >
      {label != null && <p className="mb-1 font-medium text-foreground">{String(label)}</p>}
      <div className="space-y-0.5">
        {payload.map((entry, i) => {
          const value = typeof entry.value === 'number' ? entry.value : Number(entry.value ?? 0)
          const name = String(entry.name ?? '')
          return (
            <div key={`${name}-${i}`} className="flex items-center justify-between gap-4">
              <span className="flex items-center gap-1.5 text-muted-foreground">
                <span className="size-2 rounded-full" style={{ backgroundColor: entry.color }} />
                {name}
              </span>
              <span className="tabular font-medium text-foreground">
                {valueFormatter ? valueFormatter(value, name) : value.toLocaleString()}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
