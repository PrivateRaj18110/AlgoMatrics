import { useMemo } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/layout/Panel'
import { QueryState } from '@/components/common/QueryState'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { ExecutionPipeline } from '@/components/widgets/ExecutionPipeline'
import { AXIS_TICK, CHART_COLORS } from '@/components/charts/chartTheme'
import { ChartTooltip } from '@/components/charts/ChartTooltip'
import { useExecution } from '@/hooks/useExecution'
import { formatLatency, formatTime } from '@/utils/format'
import { cn } from '@/utils/cn'
import type { ExecutionData, ExecutionResult } from '@/types'

const RESULT_VARIANT: Record<ExecutionResult, 'success' | 'warning' | 'danger'> = {
  filled: 'success',
  partial: 'warning',
  rejected: 'danger',
}

export default function ExecutionPage() {
  const query = useExecution()

  return (
    <div className="space-y-5">
      <PageHeader
        title="Execution Monitor"
        description="End-to-end order journey from signal to fill, with latency percentiles."
      />

      <QueryState query={query} loading={<ExecutionSkeleton />}>
        {(data) => <ExecutionContent data={data} />}
      </QueryState>
    </div>
  )
}

function ExecutionContent({ data }: { data: ExecutionData }) {
  const total = useMemo(() => data.latency.find((l) => l.label === 'Total Delay'), [data.latency])

  return (
    <div className="space-y-5">
      {/* Headline latency cards */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <LatencyKpi label="Median (P50)" value={total?.p50 ?? 0} />
        <LatencyKpi label="P90" value={total?.p90 ?? 0} />
        <LatencyKpi label="P95" value={total?.p95 ?? 0} />
        <LatencyKpi label="P99" value={total?.p99 ?? 0} tone="text-warning" />
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        {/* Pipeline */}
        <Panel title="Execution Pipeline" subtitle="Signal → Risk → Order → Broker → Fill">
          <ExecutionPipeline stages={data.stages} />
        </Panel>

        <div className="space-y-5">
          {/* Latency percentiles */}
          <Panel title="Latency Breakdown" subtitle="Per-leg delay percentiles (ms)" flush>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="px-4 py-2 text-left font-medium">Stage</th>
                    <th className="px-4 py-2 text-right font-medium">P50</th>
                    <th className="px-4 py-2 text-right font-medium">P90</th>
                    <th className="px-4 py-2 text-right font-medium">P95</th>
                    <th className="px-4 py-2 text-right font-medium">P99</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {data.latency.map((row) => {
                    const isTotal = row.label === 'Total Delay'
                    return (
                      <tr key={row.label} className={cn(isTotal && 'bg-muted/30 font-semibold')}>
                        <td className="px-4 py-2">{row.label}</td>
                        <td className="px-4 py-2 text-right tabular">{formatLatency(row.p50)}</td>
                        <td className="px-4 py-2 text-right tabular">{formatLatency(row.p90)}</td>
                        <td className="px-4 py-2 text-right tabular">{formatLatency(row.p95)}</td>
                        <td className="px-4 py-2 text-right tabular text-warning">
                          {formatLatency(row.p99)}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Panel>

          {/* Throughput */}
          <Panel title="Throughput" subtitle="Orders processed per minute · last hour" bodyClassName="p-2">
            <ResponsiveContainer width="100%" height={150}>
              <AreaChart data={data.throughput} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="throughputFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={CHART_COLORS.cyan} stopOpacity={0.4} />
                    <stop offset="100%" stopColor={CHART_COLORS.cyan} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="t" tick={AXIS_TICK} tickLine={false} axisLine={false} minTickGap={32} />
                <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} width={28} />
                <Tooltip content={<ChartTooltip valueFormatter={(v) => `${v} orders`} />} />
                <Area
                  type="monotone"
                  dataKey="v"
                  name="Orders/min"
                  stroke={CHART_COLORS.cyan}
                  strokeWidth={2}
                  fill="url(#throughputFill)"
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </Panel>
        </div>
      </div>

      {/* Recent executions */}
      <Panel title="Recent Executions" subtitle="Most recent order journeys" flush>
        <ScrollArea style={{ maxHeight: 360 }}>
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-card">
              <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-4 py-2 text-left font-medium">Time</th>
                <th className="px-4 py-2 text-left font-medium">Symbol</th>
                <th className="px-4 py-2 text-left font-medium">Strategy</th>
                <th className="px-4 py-2 text-right font-medium">Signal</th>
                <th className="px-4 py-2 text-right font-medium">Exec</th>
                <th className="px-4 py-2 text-right font-medium">Broker</th>
                <th className="px-4 py-2 text-right font-medium">Fill</th>
                <th className="px-4 py-2 text-right font-medium">Total</th>
                <th className="px-4 py-2 text-left font-medium">Result</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {data.recent.map((s) => (
                <tr key={s.id} className="hover:bg-accent/40">
                  <td className="px-4 py-1.5 tabular text-muted-foreground">{formatTime(s.time)}</td>
                  <td className="px-4 py-1.5 tabular font-medium">{s.symbol}</td>
                  <td className="px-4 py-1.5">{s.strategy}</td>
                  <td className="px-4 py-1.5 text-right tabular">{formatLatency(s.signalMs)}</td>
                  <td className="px-4 py-1.5 text-right tabular">{formatLatency(s.execMs)}</td>
                  <td className="px-4 py-1.5 text-right tabular">{formatLatency(s.brokerMs)}</td>
                  <td className="px-4 py-1.5 text-right tabular">{formatLatency(s.fillMs)}</td>
                  <td className="px-4 py-1.5 text-right tabular font-semibold">{formatLatency(s.totalMs)}</td>
                  <td className="px-4 py-1.5">
                    <Badge variant={RESULT_VARIANT[s.result]} className="capitalize">
                      {s.result}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollArea>
      </Panel>
    </div>
  )
}

function LatencyKpi({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn('mt-2 text-2xl font-semibold tabular', tone ?? 'text-foreground')}>
        {formatLatency(value)}
      </p>
    </Card>
  )
}

function ExecutionSkeleton() {
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Skeleton className="h-96" />
        <Skeleton className="h-96" />
      </div>
    </div>
  )
}
