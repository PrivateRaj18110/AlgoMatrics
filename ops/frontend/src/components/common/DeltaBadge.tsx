import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
import { cn } from '@/utils/cn'
import { formatSignedPercent } from '@/utils/format'
import type { Trend } from '@/types'

interface DeltaBadgeProps {
  /** Percentage change. */
  value: number
  /** When false, a negative delta is treated as "good" (e.g. drawdown). */
  higherIsBetter?: boolean
  className?: string
}

function trendOf(value: number): Trend {
  if (value > 0) return 'up'
  if (value < 0) return 'down'
  return 'flat'
}

/** Compact period-over-period delta with directional arrow + semantic colour. */
export function DeltaBadge({ value, higherIsBetter = true, className }: DeltaBadgeProps) {
  const trend = trendOf(value)
  const isGood = trend === 'flat' ? null : (trend === 'up') === higherIsBetter
  const color =
    isGood === null ? 'text-muted-foreground' : isGood ? 'text-success' : 'text-danger'
  const Icon = trend === 'up' ? ArrowUpRight : trend === 'down' ? ArrowDownRight : Minus

  return (
    <span className={cn('inline-flex items-center gap-0.5 text-xs font-medium tabular', color, className)}>
      <Icon className="size-3.5" />
      {formatSignedPercent(value)}
    </span>
  )
}
