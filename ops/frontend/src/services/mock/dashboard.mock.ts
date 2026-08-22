import type { DashboardOverview, KpiMetric, TimeSeriesPoint } from '@/types'
import { MOCK_TRADES } from './trades.mock'
import { createRng, randFloat, round } from './seed'

const rng = createRng(0xda58)

const closed = MOCK_TRADES.filter((t) => t.status === 'closed')
const open = MOCK_TRADES.filter((t) => t.status === 'open')
const wins = closed.filter((t) => t.pnl > 0)

const dayMs = 86_400_000
const now = Date.now()
const sumPnl = (since: number) =>
  round(
    MOCK_TRADES.filter((t) => new Date(t.time).getTime() >= now - since).reduce((s, t) => s + t.pnl, 0),
    0,
  )

const todayPnl = sumPnl(dayMs)
const weekPnl = sumPnl(7 * dayMs)
const monthPnl = round(closed.reduce((s, t) => s + t.pnl, 0), 0)
const yearPnl = round(monthPnl * randFloat(rng, 6.5, 9.5), 0)
const losers = closed.filter((t) => t.pnl < 0)
const winRate = round((wins.length / Math.max(closed.length, 1)) * 100, 1)
const grossWin = wins.reduce((s, t) => s + t.pnl, 0)
const grossLoss = Math.abs(losers.reduce((s, t) => s + t.pnl, 0))
const profitFactor = round(grossWin / Math.max(grossLoss, 1), 2)
const avgWin = round(grossWin / Math.max(wins.length, 1), 0)
const avgLoss = round(-grossLoss / Math.max(losers.length, 1), 0)
const exposure = round(open.reduce((s, t) => s + t.entry * t.quantity * 1000, 0), 0)

/** Equity curve: 60 sessions of compounding pnl with realistic drawdowns. */
function buildEquityCurve(start = 100_000, sessions = 60): TimeSeriesPoint[] {
  let equity = start
  const out: TimeSeriesPoint[] = []
  for (let i = sessions; i >= 0; i--) {
    const drift = randFloat(rng, -0.9, 1.25) / 100
    equity = Math.max(equity * (1 + drift), start * 0.6)
    const d = new Date(now - i * dayMs)
    out.push({ t: d.toISOString().slice(0, 10), v: round(equity, 0) })
  }
  return out
}

const equityCurve = buildEquityCurve()

/** Daily pnl bars for the last 30 sessions. */
const dailyPnl: TimeSeriesPoint[] = Array.from({ length: 30 }, (_, i) => {
  const d = new Date(now - (29 - i) * dayMs)
  return { t: d.toISOString().slice(0, 10), v: round(randFloat(rng, -3200, 5200), 0) }
})

/** Cumulative performance %, derived from the equity curve. */
const base = equityCurve[0].v
const performance: TimeSeriesPoint[] = equityCurve.map((p) => ({
  t: p.t,
  v: round(((p.v - base) / base) * 100, 2),
}))

// Drawdown calc for the KPI cards.
let peak = -Infinity
let maxDd = 0
let curDd = 0
for (const p of equityCurve) {
  peak = Math.max(peak, p.v)
  const dd = ((p.v - peak) / peak) * 100
  curDd = dd
  maxDd = Math.min(maxDd, dd)
}

const equity = equityCurve.at(-1)?.v ?? 100_000
const balance = round(equity - sumPnl(dayMs) * 0.3, 0)

const kpis: KpiMetric[] = [
  { id: 'today_pnl', label: "Today's PnL", value: todayPnl, format: 'currency', deltaPct: 4.2, trend: 'up', higherIsBetter: true },
  { id: 'week_pnl', label: 'Weekly PnL', value: weekPnl, format: 'currency', deltaPct: 8.6, trend: 'up', higherIsBetter: true },
  { id: 'month_pnl', label: 'Monthly PnL', value: monthPnl, format: 'currency', deltaPct: 12.1, trend: 'up', higherIsBetter: true },
  { id: 'year_pnl', label: 'Yearly PnL', value: yearPnl, format: 'currency', deltaPct: 21.4, trend: 'up', higherIsBetter: true },
  { id: 'equity', label: 'Equity', value: equity, format: 'currency', higherIsBetter: true },
  { id: 'balance', label: 'Balance', value: balance, format: 'currency', higherIsBetter: true },
  { id: 'open_positions', label: 'Open Positions', value: open.length, format: 'number', higherIsBetter: true },
  { id: 'closed_trades', label: 'Closed Trades', value: closed.length, format: 'number', higherIsBetter: true },
  { id: 'winning_trades', label: 'Winning Trades', value: wins.length, format: 'number', higherIsBetter: true },
  { id: 'losing_trades', label: 'Losing Trades', value: losers.length, format: 'number', higherIsBetter: false },
  { id: 'win_rate', label: 'Win Rate', value: winRate, format: 'percent', deltaPct: 1.4, trend: 'up', higherIsBetter: true },
  { id: 'profit_factor', label: 'Profit Factor', value: profitFactor, format: 'ratio', deltaPct: 0.3, trend: 'up', higherIsBetter: true },
  { id: 'avg_win', label: 'Average Win', value: avgWin, format: 'currency', higherIsBetter: true },
  { id: 'avg_loss', label: 'Average Loss', value: avgLoss, format: 'currency', higherIsBetter: true },
  { id: 'exposure', label: 'Current Exposure', value: exposure, format: 'currency', higherIsBetter: false },
  { id: 'current_dd', label: 'Current Drawdown', value: round(curDd, 1), format: 'percent', higherIsBetter: false },
  { id: 'max_dd', label: 'Maximum Drawdown', value: round(maxDd, 1), format: 'percent', higherIsBetter: false },
]

export const MOCK_DASHBOARD: DashboardOverview = {
  kpis,
  equityCurve,
  dailyPnl,
  performance,
}
