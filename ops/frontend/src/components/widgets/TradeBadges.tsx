import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/utils/cn'
import type { TradeDirection, TradeStatus } from '@/types'

/** Long / short pill with a directional arrow. */
export function DirectionBadge({ direction }: { direction: TradeDirection }) {
  const long = direction === 'long'
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 text-xs font-medium',
        long ? 'text-success' : 'text-danger',
      )}
    >
      {long ? <ArrowUpRight className="size-3.5" /> : <ArrowDownRight className="size-3.5" />}
      {long ? 'Long' : 'Short'}
    </span>
  )
}

const STATUS_VARIANT: Record<TradeStatus, 'success' | 'muted' | 'warning'> = {
  open: 'success',
  closed: 'muted',
  cancelled: 'warning',
}

const STATUS_LABEL: Record<TradeStatus, string> = {
  open: 'Open',
  closed: 'Closed',
  cancelled: 'Cancelled',
}

/** Trade lifecycle badge. */
export function TradeStatusBadge({ status }: { status: TradeStatus }) {
  return <Badge variant={STATUS_VARIANT[status]}>{STATUS_LABEL[status]}</Badge>
}
