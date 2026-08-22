import { Badge } from '@/components/ui/badge'
import { StatusDot } from './StatusDot'
import { describeStatus } from '@/utils/status'
import type { Status } from '@/types'

interface StatusBadgeProps {
  status: Status
  /** Override the label (defaults to the status name). */
  label?: string
  pulse?: boolean
}

/** Status pill combining a heartbeat dot and a coloured label. */
export function StatusBadge({ status, label, pulse = true }: StatusBadgeProps) {
  const desc = describeStatus(status)
  return (
    <Badge variant={desc.badge} className="gap-1.5">
      <StatusDot status={status} pulse={pulse} />
      {label ?? desc.label}
    </Badge>
  )
}
