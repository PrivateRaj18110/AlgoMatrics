import type { CategoryValue, RiskData } from '@/types'
import { MOCK_BROKERS } from './brokers.mock'
import { MOCK_STRATEGIES } from './strategies.mock'
import { MOCK_TRADES } from './trades.mock'
import { createRng, randFloat, round, SYMBOLS } from './seed'

const rng = createRng(0x215c)

const openTrades = MOCK_TRADES.filter((t) => t.status === 'open')

/** Notional exposure per open position, used to fan out the breakdowns. */
function notional() {
  return round(randFloat(rng, 8_000, 120_000), 0)
}

const exposureBySymbol: CategoryValue[] = SYMBOLS.slice(0, 7).map((s) => ({
  label: s,
  value: notional(),
}))

const exposureByStrategy: CategoryValue[] = MOCK_STRATEGIES.filter((s) => s.status !== 'offline')
  .slice(0, 7)
  .map((s) => ({ label: s.code, value: notional() }))

const exposureByBroker: CategoryValue[] = MOCK_BROKERS.map((b) => ({
  label: b.name,
  value: notional(),
}))

const currentExposure = round(
  exposureBySymbol.reduce((sum, e) => sum + e.value, 0),
  0,
)

export const MOCK_RISK: RiskData = {
  dailyLoss: { label: 'Daily Loss', used: round(randFloat(rng, 1_200, 6_400), 0), limit: 10_000, unit: 'currency' },
  weeklyLoss: { label: 'Weekly Loss', used: round(randFloat(rng, 4_000, 18_000), 0), limit: 30_000, unit: 'currency' },
  monthlyLoss: { label: 'Monthly Loss', used: round(randFloat(rng, 10_000, 48_000), 0), limit: 75_000, unit: 'currency' },
  currentExposure,
  maxExposure: 750_000,
  currentMargin: round(randFloat(rng, 40_000, 120_000), 0),
  marginLevelPct: round(randFloat(rng, 220, 1_400), 0),
  currentDrawdownPct: round(randFloat(rng, -8.5, -0.4), 1),
  maxDrawdownPct: round(randFloat(rng, -18, -10), 1),
  valueAtRisk: round(randFloat(rng, 12_000, 38_000), 0),
  exposureBySymbol,
  exposureByStrategy,
  exposureByBroker,
}

/** Re-export so the count of open positions can drive the risk header. */
export const RISK_OPEN_POSITIONS = openTrades.length
