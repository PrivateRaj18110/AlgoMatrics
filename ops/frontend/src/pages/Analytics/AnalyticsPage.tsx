import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/layout/Panel'
import { QueryState } from '@/components/common/QueryState'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PnlBarChart } from '@/components/charts/PnlBarChart'
import { CategoryBarChart } from '@/components/charts/CategoryBarChart'
import { Heatmap } from '@/components/charts/Heatmap'
import { CHART_COLORS } from '@/components/charts/chartTheme'
import { useAnalytics } from '@/hooks/useAnalytics'
import { formatCompactCurrency, formatLatency, formatPercent } from '@/utils/format'

export default function AnalyticsPage() {
  const query = useAnalytics()

  return (
    <div className="space-y-5">
      <PageHeader
        title="Analytics"
        description="Performance, risk and infrastructure analytics across the book."
      />

      <QueryState query={query} loading={<AnalyticsSkeleton />}>
        {(data) => (
          <div className="space-y-5">
            {/* PnL over time */}
            <Panel
              title="PnL Distribution"
              subtitle="Switch between daily, weekly and monthly horizons"
              bodyClassName="p-3"
            >
              <Tabs defaultValue="daily">
                <TabsList>
                  <TabsTrigger value="daily">Daily</TabsTrigger>
                  <TabsTrigger value="weekly">Weekly</TabsTrigger>
                  <TabsTrigger value="monthly">Monthly</TabsTrigger>
                </TabsList>
                <TabsContent value="daily">
                  <PnlBarChart data={data.dailyPnl} xType="date" height={280} />
                </TabsContent>
                <TabsContent value="weekly">
                  <PnlBarChart data={data.weeklyPnl} xType="label" height={280} />
                </TabsContent>
                <TabsContent value="monthly">
                  <PnlBarChart data={data.monthlyPnl} xType="label" height={280} />
                </TabsContent>
              </Tabs>
            </Panel>

            {/* Strategy comparisons */}
            <div className="grid gap-4 lg:grid-cols-2">
              <Panel title="Win Rate by Strategy" bodyClassName="p-3">
                <CategoryBarChart
                  data={data.winRateByStrategy}
                  name="Win Rate"
                  color={CHART_COLORS.success}
                  valueFormatter={(v) => formatPercent(v, 0)}
                />
              </Panel>
              <Panel title="Profit Factor by Strategy" bodyClassName="p-3">
                <CategoryBarChart
                  data={data.profitFactorByStrategy}
                  name="Profit Factor"
                  color={CHART_COLORS.primary}
                  valueFormatter={(v) => v.toFixed(2)}
                />
              </Panel>
            </div>

            {/* Latency + heatmaps */}
            <div className="grid gap-4 lg:grid-cols-2">
              <Panel title="Average Latency by Machine" bodyClassName="p-3">
                <CategoryBarChart
                  data={data.latencyByMachine}
                  name="Latency"
                  color={CHART_COLORS.warning}
                  valueFormatter={(v) => formatLatency(v)}
                />
              </Panel>
              <Panel title="PnL Heatmap" subtitle="Weekday × hour of day">
                <Heatmap
                  series={data.pnlHeatmap}
                  mode="diverging"
                  valueFormatter={(v) => formatCompactCurrency(v)}
                />
              </Panel>
            </div>

            <Panel title="Machine Load Heatmap" subtitle="CPU utilisation by host × hour of day">
              <Heatmap
                series={data.machineLoadHeatmap}
                mode="sequential"
                valueFormatter={(v) => `${v}%`}
              />
            </Panel>
          </div>
        )}
      </QueryState>
    </div>
  )
}

function AnalyticsSkeleton() {
  return (
    <div className="space-y-5">
      <Skeleton className="h-80 w-full" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-72" />
        <Skeleton className="h-72" />
      </div>
    </div>
  )
}
