import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { MetricCard } from '@/components/cards/MetricCard'
import { MachineCard } from '@/components/cards/MachineCard'
import { StrategyCard } from '@/components/cards/StrategyCard'
import { QueryState } from '@/components/common/QueryState'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Panel } from '@/components/layout/Panel'
import { EventTerminal } from '@/components/widgets/EventTerminal'
import { SystemStatusBar, type HealthItem } from '@/components/widgets/SystemStatusBar'
import { useDashboard } from '@/hooks/useDashboard'
import { useRecentTrades } from '@/hooks/useTrades'
import { useAlerts } from '@/hooks/useAlerts'
import { useMachines } from '@/hooks/useMachines'
import { useStrategies } from '@/hooks/useStrategies'
import { useBrokers } from '@/hooks/useBrokers'
import { useEvents } from '@/hooks/useEvents'
import { worstStatus } from '@/utils/status'
import type { Broker, Machine } from '@/types'
import { DashboardGrid } from './components/DashboardGrid'

/** Derive the subsystem health strip from live machine + broker data. */
function buildHealth(machines: Machine[], brokers: Broker[]): HealthItem[] {
  const onlineM = machines.filter((m) => m.status === 'online').length
  const onlineB = brokers.filter((b) => b.connection === 'online').length
  return [
    {
      label: 'Machine Health',
      icon: 'machine',
      status: worstStatus(machines.map((m) => m.status)),
      detail: `${onlineM}/${machines.length} online`,
    },
    {
      label: 'Broker Health',
      icon: 'broker',
      status: worstStatus(brokers.map((b) => b.connection)),
      detail: `${onlineB}/${brokers.length} connected`,
    },
    {
      label: 'Execution Health',
      icon: 'execution',
      status: 'online',
      detail: 'Nominal',
    },
    { label: 'Database', icon: 'database', status: 'online', detail: 'Connected' },
    { label: 'Data Feed', icon: 'feed', status: 'online', detail: 'Streaming' },
  ]
}

function SectionTitle({ title, to }: { title: string; to?: string }) {
  return (
    <div className="flex items-center justify-between">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">{title}</h2>
      {to && (
        <Button asChild variant="ghost" size="sm" className="h-7 gap-1 text-xs text-muted-foreground">
          <Link to={to}>
            View all <ArrowRight className="size-3.5" />
          </Link>
        </Button>
      )}
    </div>
  )
}

export default function DashboardPage() {
  const dashboard = useDashboard()
  const recentTrades = useRecentTrades(14)
  const alerts = useAlerts()
  const machines = useMachines()
  const strategies = useStrategies()
  const brokers = useBrokers()
  const events = useEvents(40)

  const health = useMemo(
    () => buildHealth(machines.data ?? [], brokers.data ?? []),
    [machines.data, brokers.data],
  )

  return (
    <div className="space-y-6">
      <PageHeader
        title="Operations Dashboard"
        description="Real-time overview of strategies, machines and trading performance."
      />

      {/* System status strip */}
      {(machines.data || brokers.data) && <SystemStatusBar items={health} />}

      {/* KPI cards */}
      <QueryState
        query={dashboard}
        loading={
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-9">
            {Array.from({ length: 9 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        }
      >
        {(data) => (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-9">
            {data.kpis.map((kpi) => (
              <MetricCard key={kpi.id} metric={kpi} />
            ))}
          </div>
        )}
      </QueryState>

      {/* Command grid: charts + trades + alerts */}
      <QueryState query={dashboard} loading={<Skeleton className="h-[560px] w-full" />}>
        {(data) => (
          <DashboardGrid
            overview={data}
            recentTrades={recentTrades.data ?? []}
            alerts={alerts.data ?? []}
          />
        )}
      </QueryState>

      {/* Live event terminal */}
      <section className="space-y-3">
        <SectionTitle title="Event Terminal" to="/events" />
        <Panel flush className="h-72" bodyClassName="min-h-0 h-full">
          <EventTerminal events={events.data ?? []} maxHeight="100%" />
        </Panel>
      </section>

      {/* Machines */}
      <section className="space-y-3">
        <SectionTitle title="Machines" to="/monitoring" />
        <QueryState
          query={machines}
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
      </section>

      {/* Strategies */}
      <section className="space-y-3">
        <SectionTitle title="Strategies" to="/strategies" />
        <QueryState
          query={strategies}
          loading={
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-60" />
              ))}
            </div>
          }
        >
          {(data) => (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {data.slice(0, 6).map((s) => (
                <StrategyCard key={s.id} strategy={s} />
              ))}
            </div>
          )}
        </QueryState>
      </section>
    </div>
  )
}
