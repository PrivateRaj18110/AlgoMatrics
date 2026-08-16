export type EodDatasetStatus =
  | 'DISCOVERED'
  | 'MANIFESTED'
  | 'UPLOADING'
  | 'PARTIAL'
  | 'VALIDATING'
  | 'READY'
  | 'COMPLETE'
  | 'FAILED'
  | 'QUARANTINED'
  | 'CONFLICT'

export type EodFileStatus = 'MANIFESTED' | 'UPLOADING' | 'READY' | 'COMPLETE' | 'FAILED' | 'CONFLICT'

export interface EodDatasetFile {
  fileId: string
  relativePath: string
  datasetType: string
  sizeBytes: number
  sha256: string
  rowCount?: number | null
  storageKey?: string | null
  bytesReceived: number
  status: EodFileStatus
  checksumStatus?: string | null
  failureReason?: string | null
  uploadedAt?: string | null
  validatedAt?: string | null
}

export interface EodDataset {
  datasetId: string
  machineId: string
  machine: string
  agentId: string
  sessionId?: string | null
  tradingDate: string
  schemaVersion: string
  manifestCreatedAt?: string | null
  status: EodDatasetStatus
  statusReason?: string | null
  storageBackend: string
  totalFiles: number
  uploadedFiles: number
  totalBytes: number
  uploadedBytes: number
  completedAt?: string | null
  finalizedAt?: string | null
  rawDeletedAt?: string | null
  receivedAt: string
  updatedAt: string
  files: EodDatasetFile[]
}

export interface EodReconciliationSummary {
  total: number
  byStatus: Record<string, number>
  missingFiles: number
  failedFiles: number
  checksumFailures: number
  partialDatasets: number
}
