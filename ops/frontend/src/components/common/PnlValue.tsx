import { cn } from '@/utils/cn'
import { formatCurrency, formatMoney } from '@/utils/format'
import type { Market } from '@/types'

interface PnlValueProps {
  value: number
  /** Render in this market's currency (INR / USD). Defaults to USD. */
  market?: Market
  /** Render with cents. */
  precise?: boolean
  /** Always show a leading +/- sign. */
  signed?: boolean
  className?: string
}

/** Profit/loss amount coloured green (positive), red (negative) or muted (flat). */
export function PnlValue({ value, market, precise, signed = true, className }: PnlValueProps) {
  const color =
    value > 0 ? 'text-success' : value < 0 ? 'text-danger' : 'text-muted-foreground'
  const text = market
    ? formatMoney(value, market, { precise, signed })
    : formatCurrency(value, { precise, signed })
  return <span className={cn('tabular font-semibold', color, className)}>{text}</span>
}
