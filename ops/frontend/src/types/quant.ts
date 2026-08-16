export interface QuantCoverage {
  datasetId: string
  tradingDate: string
  machineId: string
  sessionId?: string | null
  fileCount: number
  parsedFiles: number
  parsedRows: number
  skippedFiles: number
  datasetTypes: Record<string, number>
}

export interface QuantTradeMetrics {
  totalTrades: number
  closedTrades: number
  winningTrades: number
  losingTrades: number
  grossPnl: number
  averagePnl: number
  winRate: number
  profitFactor?: number | null
  expectancy: number
  maxDrawdown: number
  sharpeLike?: number | null
  symbols: Record<string, number>
  strategies: Record<string, number>
}

export interface QuantReplayPoint {
  t: string
  price: number
  equity?: number | null
}

export interface QuantMarketReplay {
  available: boolean
  symbol?: string | null
  points: QuantReplayPoint[]
  startTime?: string | null
  endTime?: string | null
  startPrice?: number | null
  endPrice?: number | null
  returnPct?: number | null
  high?: number | null
  low?: number | null
  maxDrawdownPct?: number | null
  volatilityPct?: number | null
}

export type QuantAnalyticsStatus = 'AVAILABLE' | 'NOT_AVAILABLE' | 'INSUFFICIENT_DATA'
export type QuantAnalyticsCategory =
  | 'performance'
  | 'strategy'
  | 'execution'
  | 'signals'
  | 'risk'
  | 'sessions'
  | 'dataQuality'

export interface QuantAnalyticsMetric {
  status: QuantAnalyticsStatus
  value?: number | string | null
  unit?: string | null
  reason?: string | null
  requiredFields: string[]
}

export interface QuantAnalyticsSection {
  status: QuantAnalyticsStatus
  calculationVersion: string
  lineage: Record<string, string | null>
  metrics: Record<string, QuantAnalyticsMetric>
  dimensions: Record<string, Record<string, number>>
  warnings: string[]
}

export interface QuantAnalyticsBundle {
  performance: QuantAnalyticsSection
  strategy: QuantAnalyticsSection
  execution: QuantAnalyticsSection
  signals: QuantAnalyticsSection
  risk: QuantAnalyticsSection
  sessions: QuantAnalyticsSection
  dataQuality: QuantAnalyticsSection
}

export interface QuantReport {
  reportId: string
  datasetId: string
  machineId: string
  tradingDate: string
  status: 'READY' | 'PARTIAL' | 'EMPTY' | 'FAILED'
  coverage: QuantCoverage
  tradeMetrics: QuantTradeMetrics
  marketReplay: QuantMarketReplay
  analytics: QuantAnalyticsBundle
  warnings: string[]
  createdAt: string
  updatedAt: string
}

export interface QuantAnalyticsReportItem {
  reportId: string
  datasetId: string
  machineId: string
  tradingDate: string
  status: QuantReport['status']
  analytics: QuantAnalyticsSection
}

export interface QuantAnalyticsSummary {
  category: QuantAnalyticsCategory
  generatedAt: string
  calculationVersion: string
  reportCount: number
  datasetId?: string | null
  reports: QuantAnalyticsReportItem[]
}

export interface SyntheticReplayRequest {
  seed: number
  symbol: string
  steps: number
  startPrice: number
  driftBps: number
  volatilityBps: number
}

export interface SyntheticReplayResult {
  seed: number
  symbol: string
  steps: number
  replay: QuantMarketReplay
  tradeMetrics: QuantTradeMetrics
}
