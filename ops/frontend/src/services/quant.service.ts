import type {
  QuantAnalyticsCategory,
  QuantAnalyticsMetric,
  QuantAnalyticsSection,
  QuantAnalyticsSummary,
  QuantReport,
  SyntheticReplayRequest,
  SyntheticReplayResult,
} from '@/types'
import { apiGet, apiPost, mockResponse, USE_MOCK } from './api/client'

const ANALYTICS_VERSION = 'phase3-quant-analytics-v1'

const DEMO_LINEAGE = {
  datasetId: 'demo-eod-2026-08-10',
  machineId: 'mch-agent-gcp-trading-01',
  tradingDate: '2026-08-10',
  sessionId: '2026-08-10-NSE',
  calculationVersion: ANALYTICS_VERSION,
}

function metric(
  status: QuantAnalyticsMetric['status'],
  value?: QuantAnalyticsMetric['value'],
  unit?: string,
  reason?: string,
  requiredFields: string[] = [],
): QuantAnalyticsMetric {
  return { status, value: value ?? null, unit, reason, requiredFields }
}

function section(
  status: QuantAnalyticsSection['status'],
  metrics: QuantAnalyticsSection['metrics'],
  dimensions: QuantAnalyticsSection['dimensions'] = {},
  warnings: string[] = [],
): QuantAnalyticsSection {
  return {
    status,
    calculationVersion: ANALYTICS_VERSION,
    lineage: DEMO_LINEAGE,
    metrics,
    dimensions,
    warnings,
  }
}

const MOCK_REPORTS: QuantReport[] = [
  {
    reportId: 'qrep-demo-eod-2026-08-10',
    datasetId: 'demo-eod-2026-08-10',
    machineId: 'mch-agent-gcp-trading-01',
    tradingDate: '2026-08-10',
    status: 'READY',
    coverage: {
      datasetId: 'demo-eod-2026-08-10',
      tradingDate: '2026-08-10',
      machineId: 'mch-agent-gcp-trading-01',
      sessionId: '2026-08-10-NSE',
      fileCount: 3,
      parsedFiles: 3,
      parsedRows: 268_420,
      skippedFiles: 0,
      datasetTypes: { ticks: 1, candles: 1, trades: 1 },
    },
    tradeMetrics: {
      totalTrades: 42,
      closedTrades: 42,
      winningTrades: 26,
      losingTrades: 16,
      grossPnl: 18450,
      averagePnl: 439.29,
      winRate: 61.9,
      profitFactor: 2.14,
      expectancy: 439.29,
      maxDrawdown: 3200,
      sharpeLike: 1.72,
      symbols: { NIFTY: 24, BANKNIFTY: 18 },
      strategies: { alpha: 28, beta: 14 },
    },
    marketReplay: {
      available: true,
      symbol: 'NIFTY',
      startTime: '2026-08-10T09:15:00+05:30',
      endTime: '2026-08-10T15:30:00+05:30',
      startPrice: 24200,
      endPrice: 24336,
      returnPct: 0.562,
      high: 24410,
      low: 24160,
      maxDrawdownPct: 0.7,
      volatilityPct: 1.8,
      points: Array.from({ length: 24 }).map((_, i) => ({
        t: `T+${i.toString().padStart(3, '0')}`,
        price: 24200 + Math.sin(i / 3) * 70 + i * 6,
      })),
    },
    analytics: {
      performance: section('AVAILABLE', {
        closedTrades: metric('AVAILABLE', 42, 'count'),
        grossPnl: metric('AVAILABLE', 18_450, 'pnl'),
        winRate: metric('AVAILABLE', 61.9, 'percent'),
        maxDrawdown: metric('AVAILABLE', 3_200, 'pnl'),
      }),
      strategy: section(
        'AVAILABLE',
        {
          tradeCount: metric('AVAILABLE', 42, 'count'),
          strategyCount: metric('AVAILABLE', 2, 'count'),
          symbolCount: metric('AVAILABLE', 2, 'count'),
        },
        { strategies: { alpha: 28, beta: 14 }, symbols: { NIFTY: 24, BANKNIFTY: 18 } },
      ),
      execution: section('AVAILABLE', {
        tradeCount: metric('AVAILABLE', 42, 'count'),
        totalFees: metric('NOT_AVAILABLE', null, undefined, 'source field is absent', [
          'fees',
          'fee',
          'commission',
          'cost',
        ]),
        averageSlippage: metric('NOT_AVAILABLE', null, undefined, 'source field is absent', [
          'slippage',
          'slippageBps',
          'slippage_bps',
        ]),
      }),
      signals: section('NOT_AVAILABLE', {
        signalCount: metric('NOT_AVAILABLE', null, undefined, 'no signal dataset was provided', [
          'signals',
        ]),
      }),
      risk: section('AVAILABLE', {
        riskEventCount: metric('NOT_AVAILABLE', null, undefined, 'no risk event dataset was provided', [
          'risk',
        ]),
        maxDrawdown: metric('AVAILABLE', 3_200, 'pnl'),
        positionCount: metric('NOT_AVAILABLE', null, undefined, 'no position dataset was provided', [
          'positions',
        ]),
      }),
      sessions: section('AVAILABLE', {
        sessionId: metric('AVAILABLE', '2026-08-10-NSE'),
        closedTrades: metric('AVAILABLE', 42, 'count'),
        parsedRows: metric('AVAILABLE', 268_420, 'count'),
      }),
      dataQuality: section('AVAILABLE', {
        parsedRows: metric('AVAILABLE', 268_420, 'count'),
        parsedFiles: metric('AVAILABLE', 3, 'count'),
        fileCoveragePct: metric('AVAILABLE', 100, 'percent'),
        skippedFiles: metric('AVAILABLE', 0, 'count'),
      }),
    },
    warnings: [],
    createdAt: new Date(Date.now() - 1000 * 60 * 20).toISOString(),
    updatedAt: new Date(Date.now() - 1000 * 60 * 20).toISOString(),
  },
]

function seeded(seed: number) {
  let state = seed >>> 0
  return () => {
    state = (1664525 * state + 1013904223) >>> 0
    return state / 2 ** 32
  }
}

function mockSynthetic(payload: SyntheticReplayRequest): SyntheticReplayResult {
  const rand = seeded(payload.seed)
  const steps = Math.min(payload.steps, 10_000)
  let price = payload.startPrice
  const points = Array.from({ length: steps }).map((_, i) => {
    if (i) {
      const centered = rand() - 0.5
      price = Math.max(0.0001, price * (1 + payload.driftBps / 10_000 + centered * payload.volatilityBps / 10_000))
    }
    return { t: `T+${i.toString().padStart(5, '0')}`, price }
  })
  const start = points[0].price
  const end = points[points.length - 1].price
  return {
    seed: payload.seed,
    symbol: payload.symbol,
    steps,
    replay: {
      available: true,
      symbol: payload.symbol,
      points,
      startTime: points[0].t,
      endTime: points[points.length - 1].t,
      startPrice: start,
      endPrice: end,
      returnPct: (end / start - 1) * 100,
      high: Math.max(...points.map((p) => p.price)),
      low: Math.min(...points.map((p) => p.price)),
      maxDrawdownPct: 0,
      volatilityPct: payload.volatilityBps / 100,
    },
    tradeMetrics: {
      totalTrades: 1,
      closedTrades: 1,
      winningTrades: end > start ? 1 : 0,
      losingTrades: end < start ? 1 : 0,
      grossPnl: end - start,
      averagePnl: end - start,
      winRate: end > start ? 100 : 0,
      profitFactor: end > start ? null : 0,
      expectancy: end - start,
      maxDrawdown: Math.max(0, start - end),
      sharpeLike: null,
      symbols: { [payload.symbol]: 1 },
      strategies: { 'synthetic-buy-hold': 1 },
    },
  }
}

function mockAnalyticsSummary(category: QuantAnalyticsCategory): QuantAnalyticsSummary {
  return {
    category,
    generatedAt: new Date().toISOString(),
    calculationVersion: ANALYTICS_VERSION,
    reportCount: MOCK_REPORTS.length,
    reports: MOCK_REPORTS.map((report) => ({
      reportId: report.reportId,
      datasetId: report.datasetId,
      machineId: report.machineId,
      tradingDate: report.tradingDate,
      status: report.status,
      analytics: report.analytics[category],
    })),
  }
}

export const quantService = {
  listReports(): Promise<QuantReport[]> {
    if (USE_MOCK) return mockResponse(MOCK_REPORTS)
    return apiGet<QuantReport[]>('/quant/reports')
  },
  getAnalytics(category: QuantAnalyticsCategory, datasetId?: string): Promise<QuantAnalyticsSummary> {
    if (USE_MOCK) return mockResponse(mockAnalyticsSummary(category))
    const params = datasetId ? `?datasetId=${encodeURIComponent(datasetId)}` : ''
    return apiGet<QuantAnalyticsSummary>(`/quant/analytics/${category}${params}`)
  },
  getDatasetReport(datasetId: string): Promise<QuantReport> {
    if (USE_MOCK) {
      return mockResponse(MOCK_REPORTS.find((report) => report.datasetId === datasetId) ?? MOCK_REPORTS[0])
    }
    return apiGet<QuantReport>(`/quant/datasets/${datasetId}/report`)
  },
  syntheticReplay(payload: SyntheticReplayRequest): Promise<SyntheticReplayResult> {
    if (USE_MOCK) return mockResponse(mockSynthetic(payload))
    return apiPost<SyntheticReplayResult>('/quant/replays/synthetic', payload)
  },
}
