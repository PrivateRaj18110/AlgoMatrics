import { useMemo, useState } from 'react'
import {
  Activity,
  BarChart3,
  BrainCircuit,
  Database,
  Play,
  ShieldAlert,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/layout/Panel'
import { QueryState } from '@/components/common/QueryState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useQuantAnalytics, useQuantReports, useSyntheticReplay } from '@/hooks/useQuant'
import type {
  QuantAnalyticsCategory,
  QuantAnalyticsStatus,
  QuantMarketReplay,
  QuantReport,
  SyntheticReplayRequest,
  SyntheticReplayResult,
} from '@/types'
import { cn } from '@/utils/cn'
import { formatNumber, formatPercent, formatRelativeTime } from '@/utils/format'

const ANALYTICS_CATEGORIES: { key: QuantAnalyticsCategory; label: string }[] = [
  { key: 'performance', label: 'Performance' },
  { key: 'strategy', label: 'Strategy' },
  { key: 'execution', label: 'Execution' },
  { key: 'signals', label: 'Signals' },
  { key: 'risk', label: 'Risk' },
  { key: 'sessions', label: 'Sessions' },
  { key: 'dataQuality', label: 'Data quality' },
]

function money(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value)
}

function statusTone(status: QuantReport['status']) {
  if (status === 'READY') return 'success'
  if (status === 'FAILED') return 'danger'
  if (status === 'PARTIAL') return 'warning'
  return 'muted'
}

function analyticsTone(status: QuantAnalyticsStatus) {
  if (status === 'AVAILABLE') return 'success'
  if (status === 'INSUFFICIENT_DATA') return 'warning'
  return 'muted'
}

function summarise(reports: QuantReport[]) {
  return {
    total: reports.length,
    rows: reports.reduce((sum, report) => sum + report.coverage.parsedRows, 0),
    pnl: reports.reduce((sum, report) => sum + report.tradeMetrics.grossPnl, 0),
    trades: reports.reduce((sum, report) => sum + report.tradeMetrics.closedTrades, 0),
  }
}

export default function QuantPage() {
  const reportsQuery = useQuantReports()
  const synthetic = useSyntheticReplay()
  const [selectedCategory, setSelectedCategory] =
    useState<QuantAnalyticsCategory>('performance')
  const analyticsQuery = useQuantAnalytics(selectedCategory)
  const [form, setForm] = useState<SyntheticReplayRequest>({
    seed: 42,
    symbol: 'SYNTH-NIFTY',
    steps: 250,
    startPrice: 100,
    driftBps: 1,
    volatilityBps: 30,
  })
  const stats = useMemo(() => summarise(reportsQuery.data ?? []), [reportsQuery.data])
  const syntheticResult = synthetic.data

  const runSynthetic = () => synthetic.mutate(form)

  return (
    <div className="space-y-5">
      <PageHeader
        title="Quant Lab"
        description="Read-only analytics and replay over finalized EOD datasets."
        actions={
          <Badge variant="outline" className="gap-1">
            <BrainCircuit className="size-3.5" />
            AWS analytics only
          </Badge>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat icon={Database} label="Reports" value={String(stats.total)} />
        <Stat icon={Activity} label="Parsed Rows" value={formatNumber(stats.rows)} />
        <Stat icon={TrendingUp} label="Closed Trades" value={formatNumber(stats.trades)} />
        <Stat icon={BarChart3} label="Gross PnL" value={money(stats.pnl)} />
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.35fr_0.9fr]">
        <QueryState
          query={reportsQuery}
          loading={
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-44" />
              ))}
            </div>
          }
        >
          {(reports) => (
            <div className="space-y-5">
              <Panel
                title="Analytics readiness"
                subtitle="Read-only derived sections materialized from EOD datasets"
              >
                <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                  {ANALYTICS_CATEGORIES.map(({ key, label }) => {
                    const counts = analyticsCounts(reports, key)
                    return (
                      <button
                        key={key}
                        type="button"
                        onClick={() => setSelectedCategory(key)}
                        className={cn(
                          'rounded-lg border border-border bg-muted/20 p-3 text-left transition hover:border-primary/50',
                          selectedCategory === key && 'border-primary/70 bg-primary/10',
                        )}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium">{label}</span>
                          <Badge variant={analyticsTone(counts.overall)}>{counts.overall}</Badge>
                        </div>
                        <p className="mt-2 text-xs text-muted-foreground">
                          {counts.available} available · {counts.notAvailable} unavailable ·{' '}
                          {counts.insufficient} insufficient
                        </p>
                      </button>
                    )
                  })}
                </div>
                <QueryState
                  query={analyticsQuery}
                  loading={<Skeleton className="mt-4 h-24" />}
                  errorTitle="Analytics summary unavailable"
                >
                  {(summary) => (
                    <div className="mt-4 rounded-lg border border-border bg-background/60 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-sm font-medium">
                          /api/quant/analytics/{summary.category}
                        </p>
                        <Badge variant="outline">{formatNumber(summary.reportCount)} reports</Badge>
                      </div>
                      <div className="mt-3 grid gap-2 md:grid-cols-2">
                        {summary.reports.slice(0, 4).map((item) => (
                          <div
                            key={item.reportId}
                            className="rounded-md border border-border bg-muted/20 p-2 text-xs"
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="truncate font-medium">{item.datasetId}</span>
                              <Badge variant={analyticsTone(item.analytics.status)}>
                                {item.analytics.status}
                              </Badge>
                            </div>
                            <p className="mt-1 text-muted-foreground">
                              {Object.keys(item.analytics.metrics).length} bounded metrics ·{' '}
                              {item.tradingDate}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </QueryState>
              </Panel>

              <Panel title="Finalized dataset reports" subtitle="Generated after EOD finalization" flush>
                {reports.length === 0 ? (
                  <div className="p-8 text-center text-sm text-muted-foreground">
                    No finalized EOD quant reports yet.
                  </div>
                ) : (
                  <div className="divide-y divide-border">
                    {reports.map((report) => (
                      <ReportRow key={report.reportId} report={report} />
                    ))}
                  </div>
                )}
              </Panel>
            </div>
          )}
        </QueryState>

        <Panel title="Synthetic replay" subtitle="Deterministic local AWS-side simulation">
          <div className="grid grid-cols-2 gap-3">
            <Field
              label="Seed"
              value={form.seed}
              onChange={(value) => setForm((f) => ({ ...f, seed: value }))}
            />
            <Field
              label="Steps"
              value={form.steps}
              onChange={(value) => setForm((f) => ({ ...f, steps: value }))}
            />
            <Field
              label="Start"
              value={form.startPrice}
              onChange={(value) => setForm((f) => ({ ...f, startPrice: value }))}
            />
            <Field
              label="Vol bps"
              value={form.volatilityBps}
              onChange={(value) => setForm((f) => ({ ...f, volatilityBps: value }))}
            />
          </div>
          <Button className="mt-4 w-full gap-2" onClick={runSynthetic} disabled={synthetic.isPending}>
            <Play className="size-4" />
            {synthetic.isPending ? 'Running…' : 'Run synthetic replay'}
          </Button>
          {synthetic.isError && (
            <p className="mt-3 text-sm text-danger">Synthetic replay failed. Check the API connection.</p>
          )}
          {syntheticResult && <SyntheticResult result={syntheticResult} />}
        </Panel>
      </div>
    </div>
  )
}

function analyticsCounts(reports: QuantReport[], category: QuantAnalyticsCategory) {
  const counts = reports.reduce(
    (acc, report) => {
      const status = report.analytics[category].status
      if (status === 'AVAILABLE') acc.available += 1
      if (status === 'NOT_AVAILABLE') acc.notAvailable += 1
      if (status === 'INSUFFICIENT_DATA') acc.insufficient += 1
      return acc
    },
    { available: 0, notAvailable: 0, insufficient: 0 },
  )
  const overall: QuantAnalyticsStatus =
    counts.available > 0
      ? 'AVAILABLE'
      : counts.insufficient > 0
        ? 'INSUFFICIENT_DATA'
        : 'NOT_AVAILABLE'
  return { ...counts, overall }
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

function Field({
  label,
  value,
  onChange,
}: {
  label: string
  value: number
  onChange: (value: number) => void
}) {
  return (
    <label className="space-y-1 text-xs text-muted-foreground">
      <span>{label}</span>
      <Input
        type="number"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="h-9"
      />
    </label>
  )
}

function ReportRow({ report }: { report: QuantReport }) {
  return (
    <div className="space-y-3 p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-sm font-semibold">{report.datasetId}</h3>
            <Badge variant={statusTone(report.status)}>{report.status}</Badge>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {report.tradingDate} · {formatNumber(report.coverage.parsedRows)} parsed rows · updated{' '}
            {formatRelativeTime(report.updatedAt)}
          </p>
        </div>
        <div className="grid grid-cols-3 gap-3 text-right text-xs">
          <Mini label="PnL" value={money(report.tradeMetrics.grossPnl)} />
          <Mini label="Win" value={formatPercent(report.tradeMetrics.winRate, 1)} />
          <Mini label="DD" value={money(report.tradeMetrics.maxDrawdown)} />
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {ANALYTICS_CATEGORIES.map(({ key, label }) => (
          <Badge key={key} variant={analyticsTone(report.analytics[key].status)} className="gap-1">
            <ShieldAlert className="size-3" />
            {label}: {report.analytics[key].status}
          </Badge>
        ))}
      </div>
      <Sparkline replay={report.marketReplay} />
      {report.warnings.length > 0 && (
        <div className="rounded-lg border border-warning/30 bg-warning/10 p-2 text-xs text-warning">
          {report.warnings.slice(0, 2).join(' · ')}
        </div>
      )}
    </div>
  )
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-muted-foreground">{label}</p>
      <p className="font-semibold tabular">{value}</p>
    </div>
  )
}

function SyntheticResult({ result }: { result: SyntheticReplayResult }) {
  return (
    <div className="mt-4 space-y-3 rounded-lg border border-border bg-muted/20 p-3">
      <div className="grid grid-cols-3 gap-2 text-xs">
        <Mini label="Return" value={formatPercent(result.replay.returnPct ?? 0, 2)} />
        <Mini label="End" value={formatNumber(result.replay.endPrice ?? 0, 2)} />
        <Mini label="Steps" value={formatNumber(result.steps)} />
      </div>
      <Sparkline replay={result.replay} compact />
    </div>
  )
}

function Sparkline({ replay, compact }: { replay: QuantMarketReplay; compact?: boolean }) {
  if (!replay.available || replay.points.length < 2) {
    return <div className="text-xs text-muted-foreground">No replay path available.</div>
  }
  const width = 320
  const height = compact ? 72 : 96
  const prices = replay.points.map((point) => point.price)
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  const span = max - min || 1
  const d = replay.points
    .map((point, index) => {
      const x = (index / (replay.points.length - 1)) * width
      const y = height - ((point.price - min) / span) * height
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={cn('w-full', compact ? 'h-20' : 'h-24')}>
      <path d={d} fill="none" stroke="currentColor" strokeWidth="2" className="text-primary" />
    </svg>
  )
}
