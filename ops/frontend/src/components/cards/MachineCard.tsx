import { memo } from 'react'
import { Activity, Cpu, Gauge, HardDrive, MemoryStick, Server, Thermometer, Wifi } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { StatusBadge } from '@/components/common/StatusBadge'
import { StatusDot } from '@/components/common/StatusDot'
import { ResourceBar } from '@/components/widgets/ResourceBar'
import type { Machine } from '@/types'
import { cn } from '@/utils/cn'
import { formatLatency, formatRelativeTime, formatUptime } from '@/utils/format'
import { describeStatus } from '@/utils/status'

interface MachineCardProps {
  machine: Machine
  className?: string
}

function Metric({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-md bg-background/40 px-2 py-1.5">
      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {icon}
        {label}
      </span>
      <span className={cn('text-xs font-medium tabular', tone ?? 'text-foreground')}>{value}</span>
    </div>
  )
}

/** Machine health card: resources, connectivity, runtime and heartbeat. */
export const MachineCard = memo(function MachineCard({ machine, className }: MachineCardProps) {
  const offline = machine.status === 'offline'
  const inactive = offline || machine.status === 'unknown'
  const heartbeatLabel = machine.lastHeartbeat
    ? `Heartbeat ${formatRelativeTime(machine.lastHeartbeat)}`
    : 'Heartbeat unknown'

  return (
    <Card className={cn('flex flex-col gap-3 p-4', className)}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <Server className="size-4.5" />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{machine.name}</p>
            <p className="truncate text-xs text-muted-foreground">{machine.location}</p>
          </div>
        </div>
        <StatusBadge status={machine.status} />
      </div>

      {/* Resource bars */}
      <div className="space-y-2">
        <ResourceBar label="CPU" value={machine.cpu} icon={<Cpu className="size-3.5" />} />
        <ResourceBar label="RAM" value={machine.ram} icon={<MemoryStick className="size-3.5" />} />
        <ResourceBar label="Disk" value={machine.disk} icon={<HardDrive className="size-3.5" />} />
      </div>

      {/* Connectivity + runtime grid */}
      <div className="grid grid-cols-2 gap-1.5">
        <Metric
          icon={<Wifi className="size-3.5" />}
          label="Internet"
          value={inactive ? '—' : formatLatency(machine.internetMs)}
        />
        <Metric
          icon={<Gauge className="size-3.5" />}
          label="Broker"
          value={inactive ? '—' : formatLatency(machine.brokerPingMs)}
        />
        <Metric
          icon={<Thermometer className="size-3.5" />}
          label="Temp"
          value={machine.temperatureC != null ? `${machine.temperatureC}°C` : 'n/a'}
        />
        <Metric
          icon={<Activity className="size-3.5" />}
          label="Python"
          value={describeStatus(machine.pythonStatus).label}
          tone={describeStatus(machine.pythonStatus).text}
        />
      </div>

      {(machine.queueDepth != null || machine.currentSessionId || machine.transportState) && (
        <div className="grid grid-cols-2 gap-1.5">
          <Metric
            icon={<Activity className="size-3.5" />}
            label="Queue"
            value={machine.queueDepth != null ? String(machine.queueDepth) : 'n/a'}
          />
          <Metric
            icon={<Server className="size-3.5" />}
            label="Transport"
            value={machine.transportState ?? 'n/a'}
          />
          <Metric
            icon={<Gauge className="size-3.5" />}
            label="Session"
            value={machine.currentSessionId ?? 'n/a'}
          />
          <Metric
            icon={<Activity className="size-3.5" />}
            label="Trading"
            value={machine.tradingProcessState ?? 'n/a'}
          />
        </div>
      )}

      {/* Footer: heartbeat + uptime */}
      <div className="mt-auto flex items-center justify-between border-t border-border pt-2.5 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <StatusDot status={machine.status} />
          {offline ? 'No heartbeat' : heartbeatLabel}
        </span>
        <span className="tabular">{inactive ? describeStatus(machine.status).label : `Up ${formatUptime(machine.uptimeSec)}`}</span>
      </div>
    </Card>
  )
})
