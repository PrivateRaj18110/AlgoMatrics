import {
  ServerCrash,
  Cpu,
  MemoryStick,
  Timer,
  Unplug,
  Bug,
  type LucideIcon,
} from 'lucide-react'
import { Check } from 'lucide-react'
import type { Alert, AlertType } from '@/types'
import { Button } from '@/components/ui/button'
import { cn } from '@/utils/cn'
import { formatRelativeTime } from '@/utils/format'
import { SEVERITY_MAP } from '@/utils/status'

const ALERT_ICON: Record<AlertType, LucideIcon> = {
  machine_offline: ServerCrash,
  high_cpu: Cpu,
  high_ram: MemoryStick,
  high_latency: Timer,
  broker_offline: Unplug,
  strategy_crash: Bug,
}

const SEVERITY_ACCENT: Record<Alert['severity'], string> = {
  critical: 'text-danger bg-danger/15',
  warning: 'text-warning bg-warning/15',
  info: 'text-primary bg-primary/15',
}

interface AlertRowProps {
  alert: Alert
  /** When provided, renders an acknowledge button for active alerts. */
  onAcknowledge?: (id: string) => void
  className?: string
}

/** Single alert line — icon, title/message, source + relative time. */
export function AlertRow({ alert, onAcknowledge, className }: AlertRowProps) {
  const Icon = ALERT_ICON[alert.type]
  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-lg border border-border/60 bg-background/40 p-3',
        alert.acknowledged && 'opacity-60',
        className,
      )}
    >
      <div className={cn('mt-0.5 rounded-md p-1.5', SEVERITY_ACCENT[alert.severity])}>
        <Icon className="size-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <p className="truncate text-sm font-medium">{alert.title}</p>
          <span className="shrink-0 text-[11px] text-muted-foreground tabular">
            {formatRelativeTime(alert.time)}
          </span>
        </div>
        <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{alert.message}</p>
        <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
          <span className="truncate">{alert.source}</span>
          <span className={cn('font-medium', SEVERITY_MAP[alert.severity].badge === 'danger' ? 'text-danger' : SEVERITY_MAP[alert.severity].badge === 'warning' ? 'text-warning' : 'text-primary')}>
            · {SEVERITY_MAP[alert.severity].label}
          </span>
          {alert.acknowledged && <span className="ml-auto text-success">· Acknowledged</span>}
        </div>
      </div>
      {onAcknowledge && !alert.acknowledged && (
        <Button
          variant="ghost"
          size="icon"
          className="size-7 shrink-0 text-muted-foreground hover:text-success"
          onClick={() => onAcknowledge(alert.id)}
          aria-label="Acknowledge alert"
        >
          <Check className="size-4" />
        </Button>
      )}
    </div>
  )
}
