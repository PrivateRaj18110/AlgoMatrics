import {
  AlertTriangle,
  Database,
  RotateCcw,
  ServerCrash,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/layout/Panel'
import { QueryState } from '@/components/common/QueryState'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useRecoverySummary } from '@/hooks/useRecovery'
import type { RecoveryMachine, RecoveryState } from '@/types'
import { cn } from '@/utils/cn'
import { formatDuration, formatNumber, formatRelativeTime } from '@/utils/format'

type BadgeVariant = 'default' | 'secondary' | 'success' | 'warning' | 'danger' | 'outline' | 'muted'

function recoveryTone(state: RecoveryState): BadgeVariant {
  if (state === 'online') return 'success'
  if (state === 'offline') return 'danger'
  if (state === 'recovering' || state === 'degraded') return 'warning'
  return 'muted'
}

export default function RecoveryPage() {
  const query = useRecoverySummary()

  return (
    <div className="space-y-5">
      <PageHeader
        title="Recovery"
        description="Offline duration, queue drain, replay gaps and EOD backlog across trading hosts."
        actions={
          <Badge variant="outline" className="gap-1">
            <ShieldCheck className="size-3.5" />
            Read-only
          </Badge>
        }
      />

      <QueryState
        query={query}
        loading={
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-24" />
              ))}
            </div>
            <Skeleton className="h-80" />
          </div>
        }
      >
        {(summary) => (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
              <Stat icon={RotateCcw} label="Recovering" value={String(summary.recovering)} />
              <Stat icon={ServerCrash} label="Offline" value={String(summary.offline)} />
              <Stat icon={AlertTriangle} label="Missing Events" value={formatNumber(summary.totalMissingEvents)} />
              <Stat icon={Database} label="EOD Backlog" value={formatNumber(summary.totalEodBacklog)} />
              <Stat icon={RotateCcw} label="Queue Depth" value={formatNumber(summary.totalQueueDepth)} />
            </div>

            <Panel
              title="Recovery state by machine"
              subtitle={`generated ${formatRelativeTime(summary.generatedAt)}`}
              flush
            >
              {summary.machines.length === 0 ? (
                <div className="p-8 text-center text-sm text-muted-foreground">
                  No machines have reported telemetry yet.
                </div>
              ) : (
                <div className="divide-y divide-border">
                  {summary.machines.map((machine) => (
                    <RecoveryRow key={machine.machineId} machine={machine} />
                  ))}
                </div>
              )}
            </Panel>
          </>
        )}
      </QueryState>
    </div>
  )
}

function Stat({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon
  label: string
  value: string
}) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <Icon className="size-3.5" />
        {label}
      </div>
      <p className="mt-2 text-xl font-semibold tabular md:text-2xl">{value}</p>
    </Card>
  )
}

function RecoveryRow({ machine }: { machine: RecoveryMachine }) {
  return (
    <div className="space-y-3 p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-sm font-semibold">{machine.machine}</h3>
            <StatusBadge status={machine.status} />
            <Badge variant={recoveryTone(machine.recoveryState)}>
              {machine.recoveryState}
            </Badge>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {machine.currentSessionId ?? 'no active session'} · {machine.transportState ?? 'transport unknown'}
          </p>
        </div>
        <div className="text-left text-xs text-muted-foreground lg:text-right">
          <p>
            Heartbeat{' '}
            {machine.lastHeartbeat ? formatRelativeTime(machine.lastHeartbeat) : 'unknown'}
          </p>
          <p>
            {machine.offlineDurationSec != null
              ? `offline ${formatDuration(machine.offlineDurationSec)}`
              : 'not offline'}
          </p>
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-4">
        <Mini label="Queue" value={machine.queueDepth != null ? formatNumber(machine.queueDepth) : 'n/a'} />
        <Mini label="Recovered" value={formatNumber(machine.eventsRecovered)} />
        <Mini label="Missing" value={formatNumber(machine.missingEvents)} />
        <Mini label="EOD Backlog" value={formatNumber(machine.eodBacklog)} />
      </div>

      {machine.warnings.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {machine.warnings.map((warning) => (
            <Badge key={warning} variant="warning" className="max-w-full truncate">
              {warning}
            </Badge>
          ))}
        </div>
      )}
    </div>
  )
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-muted/20 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={cn('mt-1 text-lg font-semibold tabular')}>{value}</p>
    </div>
  )
}
