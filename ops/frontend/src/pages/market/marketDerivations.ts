/**
 * Pure aggregation helpers shared by the market views.
 *
 * Everything here derives from the market-scoped strategy + trade fixtures, so
 * each market's Overview, Portfolio, Brokers, Analytics, Risk and Execution
 * pages stay completely independent with zero shared state.
 */
import type { CategoryValue, Strategy, TimeSeriesPoint, Trade } from '@/types'

function pct(part: number, whole: number): number {
  return whole === 0 ? 0 : Math.round((part / whole) * 1000) / 10
}

export interface MarketSummary {
  netPnl: number
  realizedPnl: number
  unrealizedPnl: number
  totalTrades: number
  closedTrades: number
  openPositions: number
  winRate: number
  profitFactor: number
  expectancy: number
  strategies: number
  onlineStrategies: number
  grossExposure: number
}

/** Headline summary for the Overview KPI band. */
export function summarise(strategies: Strategy[], trades: Trade[]): MarketSummary {
  const closed = trades.filter((t) => t.status === 'closed')
  const open = trades.filter((t) => t.status === 'open')
  const realizedPnl = closed.reduce((s, t) => s + t.pnl, 0)
  const unrealizedPnl = open.reduce((s, t) => s + t.pnl, 0)
  const wins = closed.filter((t) => t.pnl > 0)
  const grossProfit = wins.reduce((s, t) => s + t.pnl, 0)
  const grossLoss = Math.abs(closed.filter((t) => t.pnl < 0).reduce((s, t) => s + t.pnl, 0))
  return {
    netPnl: realizedPnl + unrealizedPnl,
    realizedPnl,
    unrealizedPnl,
    totalTrades: trades.length,
    closedTrades: closed.length,
    openPositions: open.length,
    winRate: pct(wins.length, closed.length),
    profitFactor: grossLoss === 0 ? grossProfit : Math.round((grossProfit / grossLoss) * 100) / 100,
    expectancy: closed.length ? Math.round(realizedPnl / closed.length) : 0,
    strategies: strategies.length,
    onlineStrategies: strategies.filter((s) => s.status === 'online').length,
    grossExposure: open.reduce((s, t) => s + Math.abs(t.entry * t.quantity), 0),
  }
}

export interface GroupStat {
  key: string
  trades: number
  netPnl: number
  winRate: number
  avgLatencyMs: number
}

function groupBy(trades: Trade[], keyOf: (t: Trade) => string): GroupStat[] {
  const map = new Map<string, Trade[]>()
  for (const t of trades) {
    const k = keyOf(t)
    const arr = map.get(k)
    if (arr) arr.push(t)
    else map.set(k, [t])
  }
  return Array.from(map.entries())
    .map(([key, ts]) => {
      const closed = ts.filter((t) => t.status === 'closed')
      const wins = closed.filter((t) => t.pnl > 0).length
      return {
        key,
        trades: ts.length,
        netPnl: ts.reduce((s, t) => s + t.pnl, 0),
        winRate: pct(wins, closed.length),
        avgLatencyMs: Math.round(ts.reduce((s, t) => s + t.latencyMs, 0) / ts.length),
      }
    })
    .sort((a, b) => b.netPnl - a.netPnl)
}

/** Performance grouped by broker. */
export function byBroker(trades: Trade[]): GroupStat[] {
  return groupBy(trades, (t) => t.broker)
}

export interface SymbolStat extends GroupStat {
  /** Net signed quantity across open positions. */
  netPosition: number
  /** Absolute notional exposure of open positions. */
  exposure: number
}

/** Performance + exposure grouped by traded symbol. */
export function bySymbol(trades: Trade[]): SymbolStat[] {
  const base = groupBy(trades, (t) => t.symbol)
  return base.map((g) => {
    const open = trades.filter((t) => t.symbol === g.key && t.status === 'open')
    return {
      ...g,
      netPosition: open.reduce((s, t) => s + (t.direction === 'long' ? t.quantity : -t.quantity), 0),
      exposure: open.reduce((s, t) => s + Math.abs(t.entry * t.quantity), 0),
    }
  })
}

/** Performance grouped by strategy name. */
export function byStrategy(trades: Trade[]): GroupStat[] {
  return groupBy(trades, (t) => t.strategy)
}

/** Cumulative realised equity curve from closed trades (oldest → newest). */
export function equitySeries(trades: Trade[]): TimeSeriesPoint[] {
  const closed = trades
    .filter((t) => t.status === 'closed')
    .slice()
    .sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime())
  let acc = 0
  return closed.map((t) => {
    acc += t.pnl
    return { t: t.time, v: Math.round(acc) }
  })
}

export interface LatencyStats {
  avg: number
  p50: number
  p95: number
  max: number
  /** Share of orders that filled (non-cancelled). */
  fillRate: number
}

function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0
  const idx = Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))
  return sorted[idx]
}

/** Execution latency distribution + fill rate. */
export function latencyStats(trades: Trade[]): LatencyStats {
  const lat = trades.map((t) => t.latencyMs).sort((a, b) => a - b)
  const filled = trades.filter((t) => t.status !== 'cancelled').length
  return {
    avg: lat.length ? Math.round(lat.reduce((s, v) => s + v, 0) / lat.length) : 0,
    p50: Math.round(percentile(lat, 50)),
    p95: Math.round(percentile(lat, 95)),
    max: lat.length ? lat[lat.length - 1] : 0,
    fillRate: pct(filled, trades.length),
  }
}

/** Convert grouped stats into chart-ready category/value pairs. */
export function toNetPnlCategories(stats: GroupStat[]): CategoryValue[] {
  return stats.map((s) => ({ label: s.key, value: s.netPnl }))
}
