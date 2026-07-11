import { cn } from '@/utils/cn'
import { describeStatus } from '@/utils/status'
import type { Status } from '@/types'

interface StatusDotProps {
  status: Status
  /** Show the animated heartbeat pulse (only meaningful when online/degraded). */
  pulse?: boolean
  className?: string
}

/** Small coloured indicator with an optional live heartbeat pulse. */
export function StatusDot({ status, pulse = true, className }: StatusDotProps) {
  const { dot, text } = describeStatus(status)
  const showPulse = pulse && status !== 'offline'
  return (
    <span className={cn('relative inline-flex size-2 items-center justify-center', className)}>
      <span className={cn('size-2 rounded-full', dot, showPulse && 'pulse-dot', text)} />
    </span>
  )
}
