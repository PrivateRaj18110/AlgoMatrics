import type { LogSource, Market } from '@/types'

/**
 * Centralised query keys keep cache invalidation consistent and typo-free.
 *
 * Market-scoped keys deliberately extend the base prefix (e.g. `['strategies',
 * 'india']`), so a broad `invalidateQueries(['strategies'])` still cascades to
 * every market.
 */
export const queryKeys = {
  dashboard: ['dashboard', 'overview'] as const,
  machines: ['machines'] as const,
  machine: (id: string) => ['machines', id] as const,
  sessions: (machineId?: string) => ['sessions', machineId ?? 'all'] as const,
  session: (sessionId: string, machineId?: string) =>
    ['sessions', sessionId, machineId ?? 'any'] as const,
  strategies: ['strategies'] as const,
  strategiesByMarket: (market: Market) => ['strategies', market] as const,
  strategy: (id: string) => ['strategies', id] as const,
  trades: ['trades'] as const,
  tradesByMarket: (market: Market) => ['trades', 'market', market] as const,
  recentTrades: (limit: number) => ['trades', 'recent', limit] as const,
  recentTradesByMarket: (limit: number, market: Market) =>
    ['trades', 'recent', limit, market] as const,
  alerts: ['alerts'] as const,
  analytics: ['analytics'] as const,
  brokers: ['brokers'] as const,
  accounts: ['accounts'] as const,
  execution: ['execution', 'overview'] as const,
  risk: ['risk', 'overview'] as const,
  events: (limit: number, filters: Record<string, unknown> = {}) => ['events', limit, filters] as const,
  eodDatasets: (filters: Record<string, unknown> = {}) => ['eod', 'datasets', filters] as const,
  eodReconciliation: ['eod', 'reconciliation'] as const,
  quantReports: ['quant', 'reports'] as const,
  quantAnalytics: (category: string, datasetId?: string) =>
    ['quant', 'analytics', category, datasetId ?? 'all'] as const,
  quantSyntheticReplay: (seed: number, steps: number) => ['quant', 'synthetic', seed, steps] as const,
  recovery: ['recovery', 'summary'] as const,
  logs: (source: LogSource | 'all', limit: number) => ['logs', source, limit] as const,
}
