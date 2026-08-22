import { useMemo } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  FileCheck2,
  Files,
  RefreshCw,
  type LucideIcon,
} from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/layout/Panel'
import { QueryState } from '@/components/common/QueryState'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useEodDatasets, useEodReconciliation } from '@/hooks/useEod'
import type { EodDataset, EodDatasetStatus, EodFileStatus } from '@/types'
import { cn } from '@/utils/cn'
import { formatNumber, formatRelativeTime } from '@/utils/format'

type BadgeVariant = 'default' | 'secondary' | 'success' | 'warning' | 'danger' | 'outline' | 'muted'

function bytes(value: number): string {
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MB`
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${value} B`
}

function pct(done: number, total: number): number {
  return total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 100
}

function datasetTone(status: EodDatasetStatus): BadgeVariant {
  if (status === 'COMPLETE' || status === 'READY') return 'success'
  if (status === 'FAILED' || status === 'CONFLICT' || status === 'QUARANTINED') return 'danger'
  if (status === 'PARTIAL' || status === 'UPLOADING' || status === 'VALIDATING') return 'warning'
  return 'muted'
}

function fileTone(status: EodFileStatus): BadgeVariant {
  if (status === 'COMPLETE' || status === 'READY') return 'success'
  if (status === 'FAILED' || status === 'CONFLICT') return 'danger'
  if (status === 'UPLOADING') return 'warning'
  return 'muted'
}

function summarise(datasets: EodDataset[]) {
  return {
    readyBytes: datasets.reduce((sum, row) => sum + row.uploadedBytes, 0),
    totalBytes: datasets.reduce((sum, row) => sum + row.totalBytes, 0),
    files: datasets.reduce((sum, row) => sum + row.totalFiles, 0),
    uploadedFiles: datasets.reduce((sum, row) => sum + row.uploadedFiles, 0),
  }
}

export default function EodPage() {
  const datasetsQuery = useEodDatasets({ limit: 100 })
  const reconciliationQuery = useEodReconciliation()
  const stats = useMemo(
    () => summarise(datasetsQuery.data ?? []),
    [datasetsQuery.data],
  )

  return (
    <div className="space-y-5">
      <PageHeader
        title="Data Sync"
        description="Read-only EOD manifest, upload, checksum and reconciliation health."
        actions={
          <Badge variant="outline" className="gap-1">
            <Database className="size-3.5" />
            Agent-fed
          </Badge>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat
          icon={Files}
          label="Datasets"
          value={String(reconciliationQuery.data?.total ?? datasetsQuery.data?.length ?? 0)}
        />
        <Stat
          icon={CheckCircle2}
          label="Complete"
          value={String(reconciliationQuery.data?.byStatus.COMPLETE ?? 0)}
        />
        <Stat
          icon={RefreshCw}
          label="Partial"
          value={String(reconciliationQuery.data?.partialDatasets ?? 0)}
        />
        <Stat
          icon={AlertTriangle}
          label="Issues"
          value={String(
            (reconciliationQuery.data?.failedFiles ?? 0) +
              (reconciliationQuery.data?.checksumFailures ?? 0),
          )}
          tone={(reconciliationQuery.data?.failedFiles ?? 0) > 0 ? 'text-danger' : undefined}
        />
        <Stat
          icon={FileCheck2}
          label="Bytes"
          value={`${bytes(stats.readyBytes)} / ${bytes(stats.totalBytes)}`}
        />
      </div>

      <QueryState
        query={datasetsQuery}
        loading={
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-40" />
            ))}
          </div>
        }
      >
        {(datasets) => (
          <Panel
            title="EOD datasets"
            subtitle={`${formatNumber(stats.uploadedFiles)} of ${formatNumber(stats.files)} files validated`}
            flush
          >
            {datasets.length === 0 ? (
              <div className="p-8 text-center text-sm text-muted-foreground">
                No EOD manifests have been received yet.
              </div>
            ) : (
              <div className="divide-y divide-border">
                {datasets.map((dataset) => (
                  <DatasetRow key={dataset.datasetId} dataset={dataset} />
                ))}
              </div>
            )}
          </Panel>
        )}
      </QueryState>
    </div>
  )
}

function Stat({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: LucideIcon
  label: string
  value: string
  tone?: string
}) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <Icon className="size-3.5" />
        {label}
      </div>
      <p className={cn('mt-2 text-xl font-semibold tabular md:text-2xl', tone)}>{value}</p>
    </Card>
  )
}

function DatasetRow({ dataset }: { dataset: EodDataset }) {
  const progress = pct(dataset.uploadedBytes, dataset.totalBytes)
  return (
    <div className="space-y-3 p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-sm font-semibold">{dataset.datasetId}</h3>
            <Badge variant={datasetTone(dataset.status)}>{dataset.status}</Badge>
            <Badge variant="muted">{dataset.storageBackend}</Badge>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {dataset.machine} · {dataset.tradingDate}
            {dataset.sessionId ? ` · ${dataset.sessionId}` : ''}
          </p>
          {dataset.statusReason && (
            <p className="mt-1 text-xs text-warning">{dataset.statusReason}</p>
          )}
        </div>
        <div className="text-left text-xs text-muted-foreground lg:text-right">
          <p>{bytes(dataset.uploadedBytes)} / {bytes(dataset.totalBytes)}</p>
          <p>updated {formatRelativeTime(dataset.updatedAt)}</p>
        </div>
      </div>

      <div>
        <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
          <span>{dataset.uploadedFiles}/{dataset.totalFiles} files checksum-ready</span>
          <span>{progress}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-muted">
          <div
            className={cn(
              'h-full rounded-full transition-all',
              dataset.status === 'FAILED' || dataset.status === 'CONFLICT'
                ? 'bg-danger'
                : dataset.status === 'COMPLETE' || dataset.status === 'READY'
                  ? 'bg-success'
                  : 'bg-warning',
            )}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      <div className="grid gap-2 lg:grid-cols-3">
        {dataset.files.map((file) => (
          <div key={file.fileId} className="rounded-lg border border-border bg-muted/20 p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-xs font-medium">{file.relativePath}</p>
                <p className="mt-0.5 text-[11px] uppercase tracking-wide text-muted-foreground">
                  {file.datasetType}
                  {typeof file.rowCount === 'number' ? ` · ${formatNumber(file.rowCount)} rows` : ''}
                </p>
              </div>
              <Badge variant={fileTone(file.status)}>{file.status}</Badge>
            </div>
            <div className="mt-3 text-xs text-muted-foreground">
              <div className="flex justify-between">
                <span>{bytes(file.bytesReceived)}</span>
                <span>{bytes(file.sizeBytes)}</span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-background">
                <div
                  className={cn(
                    'h-full rounded-full',
                    file.status === 'FAILED' || file.status === 'CONFLICT'
                      ? 'bg-danger'
                      : file.status === 'READY' || file.status === 'COMPLETE'
                        ? 'bg-success'
                        : 'bg-warning',
                  )}
                  style={{ width: `${pct(file.bytesReceived, file.sizeBytes)}%` }}
                />
              </div>
              {file.checksumStatus && <p className="mt-2">Checksum: {file.checksumStatus}</p>}
              {file.failureReason && <p className="mt-1 text-danger">{file.failureReason}</p>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
