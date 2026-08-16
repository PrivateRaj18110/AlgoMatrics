import type { EodDataset, EodReconciliationSummary } from '@/types'
import { apiGet, mockResponse, USE_MOCK } from './api/client'

export interface EodDatasetFilters {
  limit?: number
  status?: string
  machineId?: string
  tradingDate?: string
}

const EMPTY_RECONCILIATION: EodReconciliationSummary = {
  total: 0,
  byStatus: {},
  missingFiles: 0,
  failedFiles: 0,
  checksumFailures: 0,
  partialDatasets: 0,
}

const MOCK_EOD_DATASETS: EodDataset[] = [
  {
    datasetId: 'demo-eod-2026-08-10',
    machineId: 'mch-agent-gcp-trading-01',
    machine: 'gcp-trading-01',
    agentId: 'agent-demo-01',
    sessionId: '2026-08-10-NSE',
    tradingDate: '2026-08-10',
    schemaVersion: '1',
    manifestCreatedAt: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
    status: 'COMPLETE',
    statusReason: null,
    storageBackend: 'local',
    totalFiles: 3,
    uploadedFiles: 3,
    totalBytes: 12_400_000,
    uploadedBytes: 12_400_000,
    completedAt: new Date(Date.now() - 1000 * 60 * 35).toISOString(),
    finalizedAt: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
    receivedAt: new Date(Date.now() - 1000 * 60 * 46).toISOString(),
    updatedAt: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
    files: [
      {
        fileId: 'ticks',
        relativePath: 'ticks/NIFTY.csv.zst',
        datasetType: 'ticks',
        sizeBytes: 8_000_000,
        sha256: '0'.repeat(64),
        rowCount: 250_000,
        storageKey: 'demo-eod-2026-08-10/ticks.part',
        bytesReceived: 8_000_000,
        status: 'COMPLETE',
        checksumStatus: 'PASSED',
        failureReason: null,
        uploadedAt: new Date(Date.now() - 1000 * 60 * 36).toISOString(),
        validatedAt: new Date(Date.now() - 1000 * 60 * 35).toISOString(),
      },
      {
        fileId: 'candles',
        relativePath: 'candles/NIFTY-1m.parquet',
        datasetType: 'candles',
        sizeBytes: 3_200_000,
        sha256: '1'.repeat(64),
        rowCount: 18_000,
        storageKey: 'demo-eod-2026-08-10/candles.part',
        bytesReceived: 3_200_000,
        status: 'COMPLETE',
        checksumStatus: 'PASSED',
        failureReason: null,
        uploadedAt: new Date(Date.now() - 1000 * 60 * 38).toISOString(),
        validatedAt: new Date(Date.now() - 1000 * 60 * 37).toISOString(),
      },
      {
        fileId: 'trades',
        relativePath: 'trades/executions.jsonl',
        datasetType: 'trades',
        sizeBytes: 1_200_000,
        sha256: '2'.repeat(64),
        rowCount: 420,
        storageKey: 'demo-eod-2026-08-10/trades.part',
        bytesReceived: 1_200_000,
        status: 'COMPLETE',
        checksumStatus: 'PASSED',
        failureReason: null,
        uploadedAt: new Date(Date.now() - 1000 * 60 * 40).toISOString(),
        validatedAt: new Date(Date.now() - 1000 * 60 * 39).toISOString(),
      },
    ],
  },
]

function query(filters: EodDatasetFilters = {}): string {
  const params = new URLSearchParams()
  if (filters.limit) params.set('limit', String(filters.limit))
  if (filters.status) params.set('status', filters.status)
  if (filters.machineId) params.set('machineId', filters.machineId)
  if (filters.tradingDate) params.set('tradingDate', filters.tradingDate)
  const text = params.toString()
  return text ? `?${text}` : ''
}

function mockList(filters: EodDatasetFilters = {}) {
  let rows = MOCK_EOD_DATASETS
  if (filters.status) rows = rows.filter((row) => row.status === filters.status)
  if (filters.machineId) rows = rows.filter((row) => row.machineId === filters.machineId)
  if (filters.tradingDate) rows = rows.filter((row) => row.tradingDate === filters.tradingDate)
  return rows.slice(0, filters.limit ?? 100)
}

function mockReconciliation(): EodReconciliationSummary {
  return MOCK_EOD_DATASETS.reduce<EodReconciliationSummary>(
    (acc, dataset) => {
      acc.total += 1
      acc.byStatus[dataset.status] = (acc.byStatus[dataset.status] ?? 0) + 1
      acc.missingFiles += dataset.files.filter((file) => file.bytesReceived < file.sizeBytes).length
      acc.failedFiles += dataset.files.filter((file) => file.status === 'FAILED' || file.status === 'CONFLICT').length
      acc.checksumFailures += dataset.files.filter((file) => file.checksumStatus === 'FAILED').length
      if (dataset.status === 'PARTIAL' || dataset.status === 'UPLOADING') acc.partialDatasets += 1
      return acc
    },
    { ...EMPTY_RECONCILIATION, byStatus: {} },
  )
}

export const eodService = {
  list(filters: EodDatasetFilters = {}): Promise<EodDataset[]> {
    if (USE_MOCK) return mockResponse(mockList(filters))
    return apiGet<EodDataset[]>(`/eod/datasets${query(filters)}`)
  },
  get(datasetId: string): Promise<EodDataset> {
    if (USE_MOCK) {
      const row = MOCK_EOD_DATASETS.find((dataset) => dataset.datasetId === datasetId)
      return mockResponse(row ?? MOCK_EOD_DATASETS[0])
    }
    return apiGet<EodDataset>(`/eod/datasets/${datasetId}`)
  },
  reconciliation(): Promise<EodReconciliationSummary> {
    if (USE_MOCK) return mockResponse(mockReconciliation())
    return apiGet<EodReconciliationSummary>('/eod/reconciliation')
  },
}
