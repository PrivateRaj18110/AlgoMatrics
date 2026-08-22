import { Link, useParams } from 'react-router-dom'
import { Activity, AlertTriangle, Database, Radio, Server } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/layout/Panel'
import { QueryState } from '@/components/common/QueryState'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EventTerminal } from '@/components/widgets/EventTerminal'
import { useEodDatasets } from '@/hooks/useEod'
import { useEvents } from '@/hooks/useEvents'
import { useMachine } from '@/hooks/useMachines'
import { useRecoverySummary } from '@/hooks/useRecovery'
import { useSessions } from '@/hooks/useSessions'
import type { Machine } from '@/types'
import { formatDuration, formatLatency, formatNumber, formatRelativeTime } from '@/utils/format'

export default function MachineDetailPage() {
  const { machineId } = useParams()
  const machineQuery = useMachine(machineId)
  const machineFilter = machineId ? { machineId } : {}
  const eventsQuery = useEvents(80, machineFilter)
  const sessionsQuery = useSessions(machineId)
  const eodQuery = useEodDatasets({ limit: 25, machineId })
  const recoveryQuery = useRecoverySummary()
  const recovery = recoveryQuery.data?.machines.find((row) => row.machineId === machineId)

  return (
    <div className="space-y-5">
      <PageHeader
        title="Machine Detail"
        description="Read-only host, session, transport, queue, event and EOD state."
        actions={
          <Badge variant="outline" className="gap-1">
            <Server className="size-3.5" />
            No controls
          </Badge>
        }
      />

      <QueryState query={machineQuery} loading={<Skeleton className="h-72" />}>
        {(machine) =>
          machine ? (
            <>
              <MachineSummary machine={machine} />

              <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
                <Panel title="Session state" subtitle="Latest sessions reported by the agent" flush>
                  <QueryState query={sessionsQuery} loading={<Skeleton className="h-48" />}>
                    {(sessions) =>
                      sessions.length ? (
                        <div className="divide-y divide-border">
                          {sessions.map((session) => (
                            <Link
                              key={session.sessionId}
                              to={`/sessions/${encodeURIComponent(session.sessionId)}?machineId=${machine.id}`}
                              className="block p-4 transition hover:bg-muted/30"
                            >
                              <div className="flex items-center justify-between gap-3">
                                <div className="min-w-0">
                                  <p className="truncate text-sm font-semibold">
                                    {session.sessionId}
                                  </p>
                                  <p className="mt-1 text-xs text-muted-foreground">
                                    {formatNumber(session.eventCount)} events ·{' '}
                                    {formatNumber(session.tradeCount)} trades
                                  </p>
                                </div>
                                <Badge variant={session.status === 'open' ? 'success' : 'muted'}>
                                  {session.status}
                                </Badge>
                              </div>
                            </Link>
                          ))}
                        </div>
                      ) : (
                        <Empty text="No session telemetry has been reported for this machine." />
                      )
                    }
                  </QueryState>
                </Panel>

                <Panel title="Recovery signals" subtitle="Queue and replay health">
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Mini label="Recovery" value={recovery?.recoveryState ?? 'unknown'} />
                    <Mini
                      label="Queue"
                      value={recovery?.queueDepth != null ? formatNumber(recovery.queueDepth) : 'n/a'}
                    />
                    <Mini
                      label="Missing"
                      value={
                        recovery?.missingEvents != null
                          ? formatNumber(recovery.missingEvents)
                          : 'n/a'
                      }
                    />
                    <Mini
                      label="Offline"
                      value={
                        recovery?.offlineDurationSec != null
                          ? formatDuration(recovery.offlineDurationSec)
                          : 'not offline'
                      }
                    />
                  </div>
                </Panel>
              </div>

              <div className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
                <Panel title="Recent activity" subtitle="Authenticated websocket/API event timeline">
                  <QueryState query={eventsQuery} loading={<Skeleton className="h-72" />}>
                    {(events) =>
                      events.length ? (
                        <EventTerminal events={events} maxHeight={360} />
                      ) : (
                        <Empty text="No recent events for this machine." />
                      )
                    }
                  </QueryState>
                </Panel>

                <Panel title="EOD data" subtitle="Latest datasets for this machine" flush>
                  <QueryState query={eodQuery} loading={<Skeleton className="h-72" />}>
                    {(datasets) =>
                      datasets.length ? (
                        <div className="divide-y divide-border">
                          {datasets.map((dataset) => (
                            <div key={dataset.datasetId} className="p-4">
                              <div className="flex items-center justify-between gap-2">
                                <p className="truncate text-sm font-semibold">{dataset.datasetId}</p>
                                <Badge variant="outline">{dataset.status}</Badge>
                              </div>
                              <p className="mt-1 text-xs text-muted-foreground">
                                {dataset.tradingDate} · {dataset.uploadedFiles}/{dataset.totalFiles}{' '}
                                files · updated {formatRelativeTime(dataset.updatedAt)}
                              </p>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <Empty text="No EOD datasets have been received for this machine." />
                      )
                    }
                  </QueryState>
                </Panel>
              </div>
            </>
          ) : (
            <Empty text="Machine not found." />
          )
        }
      </QueryState>
    </div>
  )
}

function MachineSummary({ machine }: { machine: Machine }) {
  return (
    <div className="grid gap-3 lg:grid-cols-4">
      <Card className="p-4 lg:col-span-2">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Host
            </p>
            <h2 className="mt-1 text-lg font-semibold">{machine.name}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{machine.provider}</p>
          </div>
          <StatusBadge status={machine.status} />
        </div>
      </Card>
      <Metric
        icon={<Radio className="size-3.5" />}
        label="Heartbeat"
        value={machine.lastHeartbeat ? formatRelativeTime(machine.lastHeartbeat) : 'unknown'}
      />
      <Metric
        icon={<Activity className="size-3.5" />}
        label="Transport"
        value={machine.transportState ?? 'unknown'}
      />
      <Metric
        icon={<AlertTriangle className="size-3.5" />}
        label="Last Error"
        value={machine.lastError ? formatRelativeTime(machine.lastError) : 'none'}
      />
      <Metric
        icon={<Database className="size-3.5" />}
        label="Last EOD"
        value={machine.lastEodSync ? formatRelativeTime(machine.lastEodSync) : 'not synced'}
      />
      <Metric
        icon={<Radio className="size-3.5" />}
        label="Broker latency"
        value={formatLatency(machine.brokerPingMs)}
      />
      <Metric
        icon={<Activity className="size-3.5" />}
        label="Trading"
        value={machine.tradingProcessState ?? 'unknown'}
      />
    </div>
  )
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {icon}
        {label}
      </div>
      <p className="mt-2 text-lg font-semibold tabular">{value}</p>
    </Card>
  )
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-muted/20 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular">{value}</p>
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return <div className="p-8 text-center text-sm text-muted-foreground">{text}</div>
}
