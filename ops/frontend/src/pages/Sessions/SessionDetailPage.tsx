import { Link, useParams, useSearchParams } from 'react-router-dom'
import { CalendarClock, Database, History, Server, type LucideIcon } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/layout/Panel'
import { QueryState } from '@/components/common/QueryState'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EventTerminal } from '@/components/widgets/EventTerminal'
import { useSessionDetail } from '@/hooks/useSessions'
import { formatNumber, formatRelativeTime } from '@/utils/format'

export default function SessionDetailPage() {
  const { sessionId } = useParams()
  const [params] = useSearchParams()
  const machineId = params.get('machineId') ?? undefined
  const query = useSessionDetail(sessionId, machineId)

  return (
    <div className="space-y-5">
      <PageHeader
        title="Session Detail"
        description="Read-only session timeline, EOD linkage and replay context."
        actions={
          <Badge variant="outline" className="gap-1">
            <CalendarClock className="size-3.5" />
            No controls
          </Badge>
        }
      />

      <QueryState query={query} loading={<Skeleton className="h-96" />}>
        {(detail) => (
          <>
            <div className="grid gap-3 lg:grid-cols-4">
              <Stat icon={History} label="Events" value={formatNumber(detail.session.eventCount)} />
              <Stat icon={History} label="Trades" value={formatNumber(detail.session.tradeCount)} />
              <Stat
                icon={CalendarClock}
                label="Last Event"
                value={
                  detail.session.lastEventAt
                    ? formatRelativeTime(detail.session.lastEventAt)
                    : 'unknown'
                }
              />
              <Stat icon={Database} label="EOD Sets" value={formatNumber(detail.eodDatasets.length)} />
            </div>

            <Card className="p-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Session
                  </p>
                  <h2 className="mt-1 text-lg font-semibold">{detail.session.sessionId}</h2>
                  <p className="mt-1 text-sm text-muted-foreground">{detail.session.machine}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge variant={detail.session.status === 'open' ? 'success' : 'muted'}>
                    {detail.session.status}
                  </Badge>
                  <Badge variant="outline">
                    <Server className="size-3" />
                    {detail.session.machineId}
                  </Badge>
                </div>
              </div>
            </Card>

            <div className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
              <Panel title="Session activity" subtitle="Events reported with this session id">
                {detail.recentEvents.length ? (
                  <EventTerminal events={detail.recentEvents} maxHeight={420} />
                ) : (
                  <Empty text="No event timeline entries were found for this session." />
                )}
              </Panel>

              <Panel title="EOD linkage" subtitle="Datasets carrying this session id" flush>
                {detail.eodDatasets.length ? (
                  <div className="divide-y divide-border">
                    {detail.eodDatasets.map((dataset) => (
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
                  <Empty text="No EOD dataset has been linked to this session yet." />
                )}
              </Panel>
            </div>

            <Link
              to={`/monitoring/${detail.session.machineId}`}
              className="inline-flex text-sm text-primary hover:underline"
            >
              Back to machine detail
            </Link>
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
      <p className="mt-2 text-xl font-semibold tabular">{value}</p>
    </Card>
  )
}

function Empty({ text }: { text: string }) {
  return <div className="p-8 text-center text-sm text-muted-foreground">{text}</div>
}
