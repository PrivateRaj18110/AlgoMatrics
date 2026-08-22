import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { MachineCard } from '@/components/cards/MachineCard'
import { QueryState } from '@/components/common/QueryState'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useMachines } from '@/hooks/useMachines'
import type { Machine } from '@/types'

function summarise(machines: Machine[]) {
  const online = machines.filter((m) => m.status === 'online').length
  const avgCpu = machines.length
    ? Math.round(machines.reduce((s, m) => s + m.cpu, 0) / machines.length)
    : 0
  const strategies = machines.reduce((s, m) => s + m.strategyCount, 0)
  return { total: machines.length, online, avgCpu, strategies }
}

export default function MachinesPage() {
  const query = useMachines()
  const stats = useMemo(() => (query.data ? summarise(query.data) : null), [query.data])

  return (
    <div className="space-y-5">
      <PageHeader
        title="Machines"
        description="Infrastructure health across every VPS, cloud instance and workstation."
      />

      {stats && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Hosts" value={String(stats.total)} />
          <Stat label="Online" value={`${stats.online}/${stats.total}`} />
          <Stat label="Avg CPU" value={`${stats.avgCpu}%`} />
          <Stat label="Hosted Strategies" value={String(stats.strategies)} />
        </div>
      )}

      <QueryState
        query={query}
        loading={
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-72" />
            ))}
          </div>
        }
      >
        {(data) => (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {data.map((m) => (
              <Link key={m.id} to={`/monitoring/${m.id}`} className="block">
                <MachineCard machine={m} />
              </Link>
            ))}
          </div>
        )}
      </QueryState>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-2 text-2xl font-semibold tabular">{value}</p>
    </Card>
  )
}
