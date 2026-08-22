import { useMemo, useState } from 'react'
import { CheckCheck, ShieldCheck } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { AlertRow } from '@/components/widgets/AlertRow'
import { QueryState } from '@/components/common/QueryState'
import { EmptyState } from '@/components/common/EmptyState'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAlerts } from '@/hooks/useAlerts'
import { cn } from '@/utils/cn'
import type { Alert, Severity } from '@/types'

type Filter = 'all' | Severity

const SEVERITY_WEIGHT: Record<Severity, number> = { critical: 0, warning: 1, info: 2 }

export default function AlertsPage() {
  const query = useAlerts()
  const [filter, setFilter] = useState<Filter>('all')
  /** Local acknowledgement overlay (no backend write in mock mode). */
  const [acked, setAcked] = useState<Set<string>>(new Set())

  const merged = useMemo<Alert[]>(
    () => (query.data ?? []).map((a) => (acked.has(a.id) ? { ...a, acknowledged: true } : a)),
    [query.data, acked],
  )

  const counts = useMemo(() => {
    const active = merged.filter((a) => !a.acknowledged)
    return {
      critical: active.filter((a) => a.severity === 'critical').length,
      warning: active.filter((a) => a.severity === 'warning').length,
      info: active.filter((a) => a.severity === 'info').length,
      active: active.length,
    }
  }, [merged])

  const filtered = useMemo(
    () =>
      merged
        .filter((a) => filter === 'all' || a.severity === filter)
        .sort((a, b) => {
          if (a.acknowledged !== b.acknowledged) return a.acknowledged ? 1 : -1
          if (SEVERITY_WEIGHT[a.severity] !== SEVERITY_WEIGHT[b.severity])
            return SEVERITY_WEIGHT[a.severity] - SEVERITY_WEIGHT[b.severity]
          return new Date(b.time).getTime() - new Date(a.time).getTime()
        }),
    [merged, filter],
  )

  const acknowledge = (id: string) => setAcked((prev) => new Set(prev).add(id))
  const acknowledgeAll = () => setAcked(new Set(merged.map((a) => a.id)))

  return (
    <div className="space-y-5">
      <PageHeader
        title="Alert Center"
        description="Machine, broker and strategy alerts in one prioritised feed."
        actions={
          <Button variant="outline" size="sm" onClick={acknowledgeAll} disabled={counts.active === 0}>
            <CheckCheck className="size-4" />
            Acknowledge all
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <CountCard label="Active" value={counts.active} tone="text-foreground" />
        <CountCard label="Critical" value={counts.critical} tone="text-danger" />
        <CountCard label="Warning" value={counts.warning} tone="text-warning" />
        <CountCard label="Info" value={counts.info} tone="text-primary" />
      </div>

      <Tabs value={filter} onValueChange={(v) => setFilter(v as Filter)}>
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="critical">Critical</TabsTrigger>
          <TabsTrigger value="warning">Warning</TabsTrigger>
          <TabsTrigger value="info">Info</TabsTrigger>
        </TabsList>
      </Tabs>

      <QueryState
        query={query}
        loading={
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-20 w-full" />
            ))}
          </div>
        }
      >
        {() =>
          filtered.length === 0 ? (
            <EmptyState icon={ShieldCheck} title="No alerts" description="Nothing to show for this filter." />
          ) : (
            <div className="space-y-2">
              {filtered.map((alert) => (
                <AlertRow key={alert.id} alert={alert} onAcknowledge={acknowledge} />
              ))}
            </div>
          )
        }
      </QueryState>
    </div>
  )
}

function CountCard({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn('mt-2 text-2xl font-semibold tabular', tone)}>{value}</p>
    </Card>
  )
}
